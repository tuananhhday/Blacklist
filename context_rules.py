"""Conservative, deterministic Blacklist matching with literal evidence spans.

This module is deliberately not a language model.  A missing/ambiguous match is
forwarded to later moderation stages, never converted into a global ALLOW.
Offsets use Python/Unicode code points into the original comment (not UTF-16).
"""
from functools import lru_cache
from bisect import bisect_right
import re
import time
import unicodedata
from urllib.parse import urlsplit


MAX_TEXT = 20_000
MAX_TERMS = 40
MAX_TERM = 160
MAX_EXAMPLES = 30
MAX_EXAMPLE_CHARS = 200_000
MAX_GAP_WORDS = 8
MAX_EVIDENCE_MATCHES = 1000
CATEGORY_CODES = frozenset({
    'co_bac', 'lua_dao', 'spam', 'thu_ghet_xuc_pham',
    'khieu_dam_bao_luc', 'hang_cam', 'tin_gia',
    'an_ninh_chinh_tri', 'hai_tre_em',
})
STATUSES = frozenset({'draft', 'published', 'disabled', 'archived'})
MODES = frozenset({'signal', 'block'})
MATCH_TYPES = frozenset({'combined', 'phrase', 'domain', 'url'})
EXPECTED = frozenset({'MATCH', 'REVIEW', 'NO_MATCH'})
URL_RE = re.compile(r'https?://[^\s<>"\'“”‘’«»`]+', re.IGNORECASE)
BARE_HOST_RE = re.compile(r'(?<![\w.@-])(?:[\w-]+\.)+[\w-]+\.?(?![\w.@-])', re.UNICODE)
WORD_RE = re.compile(r'\w+', re.UNICODE)
CLAUSE_RE = re.compile(r'[.!?;:,\n\r]+')
GUARD_PATTERNS = (
    ('negation', r'đừng|chớ|không|chẳng|chưa|tránh|dừng'),
    ('reported_context',
     r'cảnh báo|phản đối|tố cáo|báo cáo|trích dẫn|đưa tin|bài báo|tin tức|'
     r'giải thích|định nghĩa|là gì|nó nhắn|nó nói|họ nói|họ nhắn|người ta nói'),
    ('mixed_context', r'nhưng|tuy nhiên|mặc dù|tuy vậy|thế nhưng'),
    ('uncertain_context', r'chưa rõ|hình như|giả sử|ví dụ'),
)
GUARD_REASONS = {
    'negation': 'Có từ phủ định như “đừng” hoặc “không”; cần người xem để tránh chặn nhầm.',
    'reported_context': 'Câu có thể đang cảnh báo, phản đối hoặc kể lại lời người khác; cần người xem.',
    'quotation': 'Có lời trong ngoặc kép; cần người xem vì đó có thể là lời được trích lại.',
    'mixed_context': 'Câu có nhiều ý chuyển hướng; cần người xem để hiểu người viết đang mời gọi hay phản đối.',
    'uncertain_context': 'Câu có ý giả định hoặc thông tin chưa rõ; cần người xem.',
    'external_context': 'Thông tin đi kèm có thể làm đổi ý nghĩa của câu; cần người xem.',
    'cross_clause': 'Từ về nội dung và lời mời hoặc hành động nằm ở hai câu/vế khác nhau; chưa chắc liên quan.',
    'distant_terms': 'Từ về nội dung và lời mời hoặc hành động cách nhau xa; chưa đủ rõ để chặn.',
    'partial_topic': 'Có từ về nội dung cần kiểm tra, nhưng chưa có lời mời hoặc hành động đi kèm.',
    'match_limit': 'Câu lặp lại quá nhiều từ cần kiểm tra; chuyển cho người xem thay vì tự chặn.',
}
SCOPE_NOTE = ('Chỉ kiểm tra các mục đang bật trong kho; chưa chạy fastText, '
              'ViSoBERT/PhoBERT và chưa kết luận bình luận an toàn.')


def _string(value, name, maximum, required=False):
    if not isinstance(value, str):
        raise ValueError(name + ' phải là văn bản.')
    value = value.strip()
    if required and not value:
        raise ValueError('Cần nhập ' + name + '.')
    if len(value) > maximum:
        raise ValueError(name + ' vượt ' + str(maximum) + ' ký tự.')
    return value


def _normalize(value):
    """NFC/casefold/space folding with a span for every normalized code point.

    Vietnamese combining marks are grouped with their preceding base before NFC
    composition.  Whitespace runs retain the full source range.  Casefold
    expansions, e.g. ß -> ss, point to the same source grapheme.
    """
    chars, spans = [], []
    index = 0
    while index < len(value):
        end = index + 1
        if value[index].isspace():
            while end < len(value) and value[end].isspace():
                end += 1
            piece = ' '
        else:
            while end < len(value) and unicodedata.category(value[end]).startswith('M'):
                end += 1
            piece = unicodedata.normalize('NFC', value[index:end]).casefold()
        for char in piece:
            chars.append(char)
            spans.append((index, end))
        index = end
    return ''.join(chars), spans


def normalize(value):
    return _normalize(value)[0].strip()


@lru_cache(maxsize=4096)
def _term_pattern(term):
    # Unicode-aware word boundaries keep a pattern out of a larger word.
    return re.compile(r'(?<!\w)' + re.escape(term) + r'(?!\w)', re.UNICODE)


def _terms(values, name):
    if not isinstance(values, list) or len(values) > MAX_TERMS:
        raise ValueError(name + ' cần là danh sách, tối đa ' + str(MAX_TERMS) + ' cụm.')
    cleaned, seen = [], set()
    for value in values:
        value = _string(value, name, MAX_TERM, required=True)
        folded = normalize(value)
        if not any(char.isalnum() for char in folded):
            raise ValueError(name + ' cần có chữ hoặc số.')
        if folded not in seen:
            seen.add(folded)
            cleaned.append(unicodedata.normalize('NFC', value))
    return cleaned


def _host(value):
    value = value.rstrip('.').casefold()
    try:
        host = value.encode('idna').decode('ascii')
    except (UnicodeError, ValueError):
        raise ValueError('Tên miền không hợp lệ.') from None
    labels = host.split('.')
    if len(host) > 253 or len(labels) < 2 or any(
            not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
            for label in labels):
        raise ValueError('Cần tên miền đầy đủ, ví dụ example.com.')
    if labels[-1].isdigit():
        raise ValueError('Cần tên miền, không dùng địa chỉ IP.')
    return host


def _url_key(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme.casefold() not in ('http', 'https') or not parsed.hostname:
            raise ValueError('URL phải có http:// hoặc https:// và tên miền.')
        if parsed.username is not None or parsed.password is not None:
            raise ValueError('URL mẫu không được chứa tên đăng nhập hoặc mật khẩu.')
        scheme = parsed.scheme.casefold()
        return (scheme, _host(parsed.hostname), parsed.port or (443 if scheme == 'https' else 80),
                unicodedata.normalize('NFC', parsed.path or '/'), parsed.query, parsed.fragment)
    except ValueError as error:
        raise ValueError(str(error) if str(error).startswith(('URL', 'Cần', 'Tên'))
                         else 'URL hoặc cổng không hợp lệ.') from None


def validate_definition(o):
    """Return a bounded, clean item; database permissions belong to the store."""
    if not isinstance(o, dict):
        raise ValueError('Mục Blacklist cần là đối tượng dữ liệu.')
    item = {
        'name': _string(o.get('name', ''), 'tên mục', 200, True),
        'category': _string(o.get('category', ''), 'nhóm vi phạm', 100, True),
        'match_type': o.get('match_type', 'combined'),
        'mode': o.get('mode', 'signal'),
        'status': o.get('status', 'draft'),
    }
    if item['category'] not in CATEGORY_CODES:
        raise ValueError('Nhóm vi phạm không tồn tại.')
    if not isinstance(item['match_type'], str) or item['match_type'] not in MATCH_TYPES:
        raise ValueError('Kiểu nhận diện không hợp lệ.')
    if not isinstance(item['mode'], str) or item['mode'] not in MODES:
        raise ValueError('Chế độ mục không hợp lệ.')
    if not isinstance(item['status'], str) or item['status'] not in STATUSES:
        raise ValueError('Trạng thái mục không hợp lệ.')
    for key in ('id', 'version'):
        if key in o:
            if type(o[key]) is not int or o[key] < 1:
                raise ValueError(key + ' không hợp lệ.')
            item[key] = o[key]
    config = o.get('config', {})
    if not isinstance(config, dict):
        raise ValueError('Điều kiện cần là đối tượng dữ liệu.')
    if item['match_type'] == 'combined':
        topics = _terms(config.get('topics', []), 'dấu hiệu nội dung')
        actions = _terms(config.get('actions', []), 'dấu hiệu hành vi')
        if not topics or not actions:
            raise ValueError('Thêm một từ về nội dung (ví dụ: cá cược) và một lời mời hoặc hành động (ví dụ: vào nhóm).')
        if {normalize(x) for x in topics} & {normalize(x) for x in actions}:
            raise ValueError('Hai ô cần chứa từ khác nhau. Ví dụ: Nội dung là cá cược, lời mời là vào nhóm.')
        item['config'] = {'topics': topics, 'actions': actions, 'pattern': ''}
    else:
        pattern = _string(config.get('pattern', ''), 'cụm hoặc địa chỉ nhận diện',
                          2048 if item['match_type'] == 'url' else 500, True)
        if item['match_type'] == 'domain':
            if any(char in pattern for char in '/:@?#') or any(char.isspace() for char in pattern):
                raise ValueError('Chỉ nhập tên miền, không có giao thức, đường dẫn hoặc cổng.')
            pattern = _host(pattern)
        elif item['match_type'] == 'url':
            if any(char.isspace() for char in pattern):
                raise ValueError('URL không được chứa khoảng trắng.')
            _url_key(pattern)
        elif not any(char.isalnum() for char in pattern):
            raise ValueError('Cụm nhận diện cần có chữ hoặc số.')
        item['config'] = {'topics': [], 'actions': [], 'pattern': unicodedata.normalize('NFC', pattern)}
    examples = o.get('examples', [])
    if not isinstance(examples, list) or len(examples) > MAX_EXAMPLES:
        raise ValueError('Tối đa ' + str(MAX_EXAMPLES) + ' ví dụ cho một mục.')
    cleaned, total = [], 0
    for example in examples:
        if not isinstance(example, dict):
            raise ValueError('Ví dụ cần là đối tượng dữ liệu.')
        text = _string(example.get('text', ''), 'câu ví dụ', MAX_TEXT, True)
        context = _string(example.get('context', ''), 'ngữ cảnh ví dụ', MAX_TEXT)
        expected = example.get('expected')
        if not isinstance(expected, str) or expected not in EXPECTED:
            raise ValueError('Chọn cách xử lý cho câu ví dụ: Chặn, Cần người xem hoặc Cho đi tiếp.')
        total += len(text) + len(context)
        if total > MAX_EXAMPLE_CHARS:
            raise ValueError('Tổng nội dung ví dụ vượt giới hạn.')
        row = {'text': text, 'context': context, 'expected': expected}
        # Store resolves/validates provenance; preserve bounded references only.
        for key in ('source_sample_id', 'source_review_id'):
            if example.get(key) is not None:
                if type(example[key]) is not int or example[key] < 1:
                    raise ValueError('Nguồn ví dụ không hợp lệ.')
                row[key] = example[key]
        cleaned.append(row)
    item['examples'] = cleaned
    return item


def _url_ranges(text):
    found = []
    for match in URL_RE.finditer(text):
        url = match.group().rstrip('.,;:!?)]}')
        if url:
            found.append((match.start(), match.start() + len(url), url))
    return found


def _clauses(text, urls):
    spans, start = [], 0
    for match in CLAUSE_RE.finditer(text):
        if any(a <= match.start() < b for a, b, _ in urls):
            continue
        if match.start() > start:
            spans.append((start, match.start()))
        start = match.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def _evidence(text, spans, start, end, role):
    a, b = spans[start][0], spans[end - 1][1]
    return {'start': a, 'end': b, 'text': text[a:b], 'role': role}


def _find_terms(text, folded, spans, terms, role):
    result = []
    for term in terms:
        for match in _term_pattern(normalize(term)).finditer(folded):
            if len(result) >= MAX_EVIDENCE_MATCHES:
                return result, True
            result.append(_evidence(text, spans, match.start(), match.end(), role))
    return result, False


def _guards(text, folded, spans, context):
    guards, evidence = [], []
    for code, expression in GUARD_PATTERNS:
        match = re.search(r'(?<!\w)(?:' + expression + r')(?!\w)', folded)
        if match:
            guards.append(code)
            evidence.append(_evidence(text, spans, match.start(), match.end(), 'context'))
    if any(char in text for char in '"“”‘’«»`\''):
        guards.append('quotation')
    if context:
        context_folded = normalize(context)
        if (any(char in context for char in '"“”‘’«»`\'') or
                any(re.search(r'(?<!\w)(?:' + expression + r')(?!\w)', context_folded)
                    for _, expression in GUARD_PATTERNS)):
            guards.append('external_context')
    return guards, evidence


def _prepare(text, context):
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Nhập bình luận để kiểm tra.')
    if not isinstance(context, str):
        raise ValueError('Ngữ cảnh phải là văn bản.')
    if len(text) > MAX_TEXT or len(context) > MAX_TEXT:
        raise ValueError('Bình luận và ngữ cảnh tối đa ' + str(MAX_TEXT) + ' ký tự mỗi phần.')
    folded, spans = _normalize(text)
    urls = _url_ranges(text)
    guards, guard_evidence = _guards(text, folded, spans, context)
    return {'text': text, 'folded': folded, 'spans': spans, 'urls': urls,
            'clauses': _clauses(text, urls), 'guards': guards, 'guard_evidence': guard_evidence}


def _clause(evidence, clauses):
    low, high = 0, len(clauses)
    while low < high:
        middle = (low + high) // 2
        if clauses[middle][0] <= evidence['start']:
            low = middle + 1
        else:
            high = middle
    index = low - 1
    if index >= 0 and evidence['end'] <= clauses[index][1]:
        return index
    return None


def _near_pairs(topics, actions, clauses, text):
    """Find lexical proximity without a Cartesian product of all matches.

    For each topic, only the closest following action and the prior/overlapping
    action with the furthest end can minimize the gap.  A bounded explanation
    needs at most 100 pairs even when thousands of repeated spans match.
    """
    grouped_topics, grouped_actions = {}, {}
    for spans, groups in ((topics, grouped_topics), (actions, grouped_actions)):
        for span in spans:
            index = _clause(span, clauses)
            if index is not None:
                groups.setdefault(index, []).append(span)
    shared = grouped_topics.keys() & grouped_actions.keys()
    close = []
    for index in shared:
        ordered = sorted(grouped_actions[index], key=lambda e: e['start'])
        starts = [span['start'] for span in ordered]
        furthest, best = [], ordered[0]
        for span in ordered:
            if span['end'] > best['end']:
                best = span
            furthest.append(best)
        for topic in grouped_topics[index]:
            split = bisect_right(starts, topic['end'])
            candidates = ([furthest[split - 1]] if split else [])
            if split < len(ordered):
                candidates.append(ordered[split])
            for action in candidates:
                left, right = sorted((topic, action), key=lambda e: e['start'])
                gap = text[left['end']:right['start']] if left['end'] <= right['start'] else ''
                if len(WORD_RE.findall(gap)) <= MAX_GAP_WORDS:
                    close.append((topic, action))
                    if len(close) >= 100:
                        return True, close
    return bool(shared), close


def _deduplicate(evidence):
    result, seen = [], set()
    for span in sorted(evidence, key=lambda e: (e['start'], e['end'], e['role'])):
        key = (span['start'], span['end'], span['role'])
        if key not in seen:
            seen.add(key)
            result.append(span)
    return result[:200]


def _address_matches(item, prepared):
    text, pattern = prepared['text'], item['config']['pattern']
    evidence = []
    if item['match_type'] == 'url':
        target = _url_key(pattern)
        for start, end, value in prepared['urls']:
            try:
                if _url_key(value) == target:
                    evidence.append({'start': start, 'end': end, 'text': text[start:end], 'role': 'url'})
            except ValueError:
                continue
        return evidence
    target = _host(pattern)
    for start, end, value in prepared['urls']:
        try:
            parsed = urlsplit(value)
            if parsed.hostname and _host(parsed.hostname) == target:
                authority_start = value.index('://') + 3
                authority = parsed.netloc
                host_part = authority.rsplit('@', 1)[-1]
                # Exclude userinfo and ports from the highlighted hostname.
                offset = authority_start + len(authority) - len(host_part)
                hostname = host_part.rsplit(':', 1)[0] if ':' in host_part else host_part
                host_start, host_end = start + offset, start + offset + len(hostname)
                evidence.append({'start': host_start, 'end': host_end,
                                 'text': text[host_start:host_end], 'role': 'domain'})
        except (ValueError, UnicodeError):
            continue
    # Bare hosts are useful in copied comments. Never find a target inside a
    # different hostname, email address, or an URL's userinfo/path/query.
    for match in BARE_HOST_RE.finditer(prepared['folded']):
        span = _evidence(text, prepared['spans'], match.start(), match.end(), 'domain')
        if any(a <= span['start'] < b for a, b, _ in prepared['urls']):
            continue
        try:
            if _host(match.group()) == target:
                evidence.append(span)
        except ValueError:
            continue
    return evidence


def _evaluate(item, prepared):
    text, folded, spans = prepared['text'], prepared['folded'], prepared['spans']
    result = {'result': 'NO_MATCH', 'evidence': [], 'reasons': [], 'ambiguities': [],
              'rule_id': item.get('id'), 'rule_version': item.get('version', 1),
              'category': item['category'], 'name': item['name'], 'mode': item.get('mode', 'signal')}
    ambiguities, evidence = [], []
    kind, config = item['match_type'], item['config']
    if kind == 'combined':
        topics, topics_limited = _find_terms(text, folded, spans, config['topics'], 'topic')
        if not topics:
            result['reasons'] = ['Câu chưa có từ về nội dung mà mục này đang tìm.']
            return result
        actions, actions_limited = _find_terms(text, folded, spans, config['actions'], 'action')
        if topics_limited or actions_limited:
            ambiguities.append('match_limit')
        evidence = topics + actions
        if not actions:
            ambiguities.append('partial_topic')
        else:
            same_clause, close = _near_pairs(topics, actions, prepared['clauses'], text)
            if not same_clause:
                ambiguities.append('cross_clause')
            elif not close:
                ambiguities.append('distant_terms')
            else:
                evidence = [span for pair in close for span in pair]
    elif kind == 'phrase':
        evidence, limited = _find_terms(text, folded, spans, [config['pattern']], 'pattern')
        if limited:
            ambiguities.append('match_limit')
        if evidence and all(_clause(span, prepared['clauses']) is None for span in evidence):
            ambiguities.append('cross_clause')
    else:
        evidence = _address_matches(item, prepared)
    if not evidence:
        result['reasons'] = ['Câu chưa có cụm từ hoặc địa chỉ mà mục này đang tìm.']
        return result
    ambiguities = list(dict.fromkeys(ambiguities + prepared['guards']))
    evidence += prepared['guard_evidence']
    result['evidence'] = _deduplicate(evidence)
    result['ambiguities'] = ambiguities
    result['reasons'] = [GUARD_REASONS[code] for code in ambiguities]
    if ambiguities or item.get('mode', 'signal') != 'block':
        result['result'] = 'REVIEW'
        if item.get('mode', 'signal') != 'block':
            result['reasons'].append('Mục này đang đặt Chỉ nhắc người duyệt nên không tự chặn.')
    else:
        result['result'] = 'MATCH'
        result['reasons'] = ['Câu có đủ các từ mục này đang tìm và chưa thấy dấu hiệu cần người xem.']
    return result


def evaluate_item(item, text, context=''):
    """Recognize one definition, including drafts used in the editor.

    Lifecycle authorization is deliberately enforced by evaluate_bank/store.
    A draft's MATCH is not itself a BLOCK or a publication action.
    """
    return _evaluate(validate_definition(item), _prepare(text, context))


def evaluate_examples(item):
    """Compare intrinsic recognition, independent of runtime mode/lifecycle.

    Positive example MATCH means all lexical conditions are met without a
    context guard.  REVIEW is the correct target for warning/quoted/partial
    matches; unrelated text is NO_MATCH.  The temporary copy is never saved.
    """
    clean = validate_definition(item)
    reference = dict(clean, mode='block', status='published')
    rows = []
    for example in clean['examples']:
        evaluation = _evaluate(reference, _prepare(example['text'], example.get('context', '')))
        rows.append(dict(example, actual=evaluation['result'],
                         passed=evaluation['result'] == example['expected'], evaluation=evaluation))
    return rows


def evaluate_bank(items, text, context=''):
    started = time.perf_counter()
    prepared = _prepare(text, context)
    matches, checked = [], 0
    for item in items:
        if item.get('status') != 'published':
            continue
        checked += 1
        evaluation = _evaluate(validate_definition(item), prepared)
        if evaluation['result'] != 'NO_MATCH':
            matches.append(evaluation)
    blockers = [match for match in matches if match['result'] == 'MATCH' and match['mode'] == 'block']
    if blockers:
        decision, next_stage = 'BLOCK', 'none'
        headline = 'Đề xuất chặn theo Blacklist'
        explanation = ('Có ' + str(len(blockers)) + ' mục đang bật chặn tìm thấy đủ các từ cần kiểm tra. '
                       'Đây là kết quả thử Blacklist; khi áp dụng thực tế vẫn cần bước kiểm tra chặn nhầm.')
    elif matches:
        decision, next_stage = 'REVIEW', 'fasttext'
        headline = 'Cần người xem thêm'
        explanation = 'Câu có từ liên quan nhưng chưa rõ có nên chặn. Trong luồng đầy đủ, câu này cần được kiểm tra tiếp trước khi người duyệt quyết định.'
    else:
        decision, next_stage = 'NO_MATCH', 'fasttext'
        headline = 'Cho đi tiếp qua Blacklist' if checked else 'Kho chưa có mục đang bật'
        explanation = ('Câu chưa có các từ mà kho đang tìm; cho đi tiếp sang bước kiểm tra sau. Kết quả này '
                       'chưa có nghĩa là bình luận an toàn.' if checked else
                       'Hãy tạo một mục, thử các câu ví dụ rồi bật vào kho để kiểm tra bình luận. Kho trống chưa thể kết luận an toàn.')
    return {'decision': decision, 'headline': headline, 'explanation': explanation,
            'matches': matches, 'checked_count': checked,
            'elapsed_ms': round((time.perf_counter() - started) * 1000, 3),
            'next_stage': next_stage, 'scope_note': SCOPE_NOTE}
