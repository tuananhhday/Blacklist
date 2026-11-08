"""Meaningful lexical/context/URL regressions; no trained-model claims."""
import copy
import unicodedata
import unittest

import context_rules as rules


def item(**changes):
    row = {'id': 4, 'name': 'Cờ bạc · Mời gọi', 'category': 'co_bac',
           'version': 2, 'status': 'published', 'mode': 'block',
           'match_type': 'combined',
           'config': {'topics': ['cá cược', 'cá độ'], 'actions': ['vào nhóm', 'tham gia']},
           'examples': []}
    row.update(changes)
    return row


class ContextRules(unittest.TestCase):
    def test_direct_invite_and_literal_evidence(self):
        text = 'Mời bạn VÀO   NHÓM cá cược nhận thưởng.'
        result = rules.evaluate_bank([item()], text)
        self.assertEqual(result['decision'], 'BLOCK')
        self.assertEqual(result['next_stage'], 'none')
        self.assertEqual(result['checked_count'], 1)
        self.assertEqual({e['role'] for e in result['matches'][0]['evidence']}, {'topic', 'action'})
        for span in result['matches'][0]['evidence']:
            self.assertEqual(text[span['start']:span['end']], span['text'])

    def test_warning_negation_and_invitation_using_negation_are_deferred(self):
        cases = [
            'Đừng tham gia nhóm cá cược.',
            'Cảnh báo: vào nhóm cá cược dễ mất tiền.',
            'Đừng bỏ lỡ kèo ngon, vào nhóm cá cược ngay.',
            'Không cần vốn, vào nhóm cá độ ngay.',
            'Tôi phản đối cá cược. Nhưng ai muốn thì vào nhóm này.',
            'Nó nhắn “vào nhóm cá cược”, tôi báo cáo rồi.',
            'Vào nhóm cá cược nhé',
        ]
        for text in cases[:-1]:
            with self.subTest(text=text):
                outcome = rules.evaluate_bank([item()], text)
                self.assertEqual(outcome['decision'], 'REVIEW')
                self.assertEqual(outcome['next_stage'], 'fasttext')
                self.assertTrue(outcome['matches'][0]['ambiguities'])
        self.assertEqual(rules.evaluate_bank([item()], cases[-1])['decision'], 'BLOCK')

    def test_partial_distant_and_cross_clause_are_review(self):
        for text, expected_code in [
            ('Tôi nhắc đến cá cược.', 'partial_topic'),
            ('Cá cược. Vào nhóm học tập.', 'cross_clause'),
            ('Vào nhóm một hai ba bốn năm sáu bảy tám chín mười rồi nói cá cược.', 'distant_terms'),
        ]:
            with self.subTest(text=text):
                result = rules.evaluate_item(item(), text)
                self.assertEqual(result['result'], 'REVIEW')
                self.assertIn(expected_code, result['ambiguities'])
        self.assertEqual(rules.evaluate_item(item(), 'Vào nhóm học tập.')['result'], 'NO_MATCH')

    def test_repetitive_comment_is_bounded_and_deferred(self):
        row = item(config={'topics': ['a'], 'actions': ['b']})
        # Under the text limit, but thousands of each span would create tens
        # of millions of Cartesian pairs in an unbounded implementation.
        text = 'a b ' * 4500
        result = rules.evaluate_item(row, text)
        self.assertEqual(result['result'], 'REVIEW')
        self.assertIn('match_limit', result['ambiguities'])
        self.assertLessEqual(len(result['evidence']), 200)
        for span in result['evidence']:
            self.assertEqual(text[span['start']:span['end']], span['text'])

    def test_overlapping_action_and_multiple_clauses_find_nearest_pair(self):
        row = item(config={
            'topics': ['cá cược'],
            'actions': ['vào nhóm cá cược để nhận thưởng', 'nhận thưởng'],
        })
        result = rules.evaluate_item(row, 'Chào bạn. Vào nhóm cá cược để nhận thưởng ngay.')
        self.assertEqual(result['result'], 'MATCH')
        self.assertEqual({span['role'] for span in result['evidence']}, {'topic', 'action'})

    def test_word_boundaries_preserve_accents(self):
        row = item(match_type='phrase', config={'pattern': 'cá độ'})
        self.assertEqual(rules.evaluate_item(row, 'Có một bể cá độn thêm đá.')['result'], 'NO_MATCH')
        self.assertEqual(rules.evaluate_item(row, 'ca do') ['result'], 'NO_MATCH')
        self.assertEqual(rules.evaluate_item(row, 'CÁ ĐỘ!')['result'], 'MATCH')

    def test_unicode_decomposition_emoji_and_casefold_have_original_offsets(self):
        text = '🙂 ' + unicodedata.normalize('NFD', 'VÀO NHÓM CÁ CƯỢC') + ' nhé.'
        result = rules.evaluate_item(item(), text)
        self.assertEqual(result['result'], 'MATCH')
        for span in result['evidence']:
            self.assertEqual(text[span['start']:span['end']], span['text'])
            self.assertGreaterEqual(span['start'], 2)
        row = item(match_type='phrase', config={'pattern': 'strasse'})
        span = rules.evaluate_item(row, '🙂 Straße!')['evidence'][0]
        self.assertEqual(span['text'], 'Straße')

    def test_lifecycle_and_signal_mode_never_block(self):
        text = 'Vào nhóm cá cược ngay.'
        for status in ['draft', 'disabled', 'archived']:
            self.assertEqual(rules.evaluate_bank([item(status=status)], text)['decision'], 'NO_MATCH')
        result = rules.evaluate_bank([item(mode='signal')], text)
        self.assertEqual(result['decision'], 'REVIEW')
        self.assertEqual(result['matches'][0]['result'], 'REVIEW')
        self.assertEqual(rules.evaluate_item(item(status='draft'), text)['result'], 'MATCH')
        self.assertEqual(rules.evaluate_bank([], text)['decision'], 'NO_MATCH')
        self.assertIn('chưa', rules.evaluate_bank([], text)['scope_note'])

    def test_strong_rule_dominates_review_without_dropping_matches(self):
        result = rules.evaluate_bank([item(mode='signal', id=1), item(id=2)], 'Vào nhóm cá cược.')
        self.assertEqual(result['decision'], 'BLOCK')
        self.assertEqual(len(result['matches']), 2)
        self.assertEqual(result['checked_count'], 2)

    def test_exact_domain_not_suffix_userinfo_path_query_or_email(self):
        row = item(match_type='domain', config={'pattern': 'casino.example'})
        for text in ['https://casino.example/register', 'casino.example/register', 'casino.example.',
                     'https://CASINO.EXAMPLE:443/register']:
            result = rules.evaluate_item(row, text)
            self.assertEqual(result['result'], 'MATCH', text)
            for span in result['evidence']:
                self.assertEqual(text[span['start']:span['end']], span['text'])
        for text in ['https://casino.example.evil.com', 'https://notcasino.example',
                     'https://sub.casino.example', 'https://casino.example@safe.example',
                     'https://safe.example/casino.example',
                     'https://safe.example/?next=casino.example', 'casino.example@safe.example']:
            self.assertEqual(rules.evaluate_item(row, text)['result'], 'NO_MATCH', text)

    def test_idna_domain_has_literal_unicode_spans(self):
        row = item(match_type='domain', config={'pattern': 'cá.example'})
        for text in ['https://CÁ.example/a', 'cá.example.', unicodedata.normalize('NFD', 'CÁ.example')]:
            result = rules.evaluate_item(row, text)
            self.assertEqual(result['result'], 'MATCH', text)
            self.assertEqual(result['evidence'][0]['text'], text[result['evidence'][0]['start']:result['evidence'][0]['end']])

    def test_url_exactness_and_periods_inside_links(self):
        row = item(match_type='url', config={'pattern': 'https://casino.example/Register?a=1'})
        self.assertEqual(rules.evaluate_item(row, 'Mở https://casino.example/Register?a=1.')['result'], 'MATCH')
        self.assertEqual(rules.evaluate_item(row, 'https://casino.example/register?a=1')['result'], 'NO_MATCH')
        self.assertEqual(rules.evaluate_item(row, 'https://casino.example/Register?a=2')['result'], 'NO_MATCH')
        combined = item(config={'topics': ['casino.example'], 'actions': ['vào nhóm']})
        self.assertEqual(rules.evaluate_item(combined, 'Vào nhóm https://casino.example nhé.')['result'], 'MATCH')

    def test_context_guards_apply_to_phrase_domain_and_url(self):
        for kind, pattern, text in [
            ('phrase', 'vào nhóm cá cược', 'Đừng vào nhóm cá cược.'),
            ('domain', 'casino.example', 'Cảnh báo https://casino.example là trang giả.'),
            ('url', 'https://casino.example/', 'Nó nhắn “https://casino.example/”.'),
        ]:
            result = rules.evaluate_item(item(match_type=kind, config={'pattern': pattern}), text)
            self.assertEqual(result['result'], 'REVIEW')
        result = rules.evaluate_item(item(), 'Vào nhóm cá cược.', 'Người trước đang cảnh báo về nhóm này.')
        self.assertEqual(result['result'], 'REVIEW')
        self.assertIn('external_context', result['ambiguities'])

    def test_examples_test_recognition_independent_of_mode(self):
        row = item(mode='signal', status='draft', examples=[
            {'text': 'Vào nhóm cá cược.', 'expected': 'MATCH'},
            {'text': 'Đừng tham gia cá cược.', 'expected': 'REVIEW'},
            {'text': 'Xin chào mọi người.', 'expected': 'NO_MATCH'},
        ])
        results = rules.evaluate_examples(row)
        self.assertTrue(all(result['passed'] for result in results))
        self.assertEqual(row['mode'], 'signal')
        self.assertEqual(row['status'], 'draft')

    def test_validation_limits_and_malformed_conditions(self):
        cases = [item(category='unknown'), item(mode='auto'), item(mode=[]), item(status='active'),
                 item(match_type='regex'), item(config={'topics': ['cá cược'], 'actions': []}),
                 item(config={'topics': ['cá cược'], 'actions': ['CÁ CƯỢC']}),
                 item(config={'topics': ['x'] * 41, 'actions': ['mời']}),
                 item(match_type='domain', config={'pattern': 'https://casino.example'}),
                 item(match_type='domain', config={'pattern': 'casino.example@safe.example'}),
                 item(match_type='url', config={'pattern': 'javascript:alert(1)'}),
                 item(match_type='url', config={'pattern': 'https://user:password@casino.example'}),
                 item(examples=[{'text': 'x', 'expected': 'ALLOW'}]), item(version=True)]
        for row in cases:
            with self.subTest(row=row):
                with self.assertRaises(ValueError):
                    rules.validate_definition(row)
        with self.assertRaises(ValueError):
            rules.evaluate_item(item(), 'x' * (rules.MAX_TEXT + 1))
        with self.assertRaises(ValueError):
            rules.evaluate_bank([], '')
        cleaned = rules.validate_definition(item(config={'topics': ['cá cược', 'CÁ CƯỢC'], 'actions': ['vào nhóm']}))
        self.assertEqual(cleaned['config']['topics'], ['cá cược'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
