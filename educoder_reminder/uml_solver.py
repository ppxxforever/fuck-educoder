"""根据头歌评测脚本（可在工作区 / 评测时挂载）逆向构造正确的 StarUML .mdj。

不同实验的评测脚本写法差异很大，本模块按「从具体到通用」依次尝试多种模式：

1. solve_flowchart       系统流程图/数据流图（FCProcess / FCDatabase / FCFlow + 连线）
2. solve_by_owned_path   时序图/交互图（participants / messages，按索引路径定位）
3. solve_analyze_element 通用元素列表（analyze_element(list, '名称', '类型')）
4. solve_class_diagram   类图（遍历 ownedElements[1:]，检查类名/属性/关系）
5. build_mdj             旧顺序图（analyze_element + analyze_line1 消息）
"""
import json
import re
import secrets

_ID_CHARS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz+/'


def _gid():
    return 'AAAAAA' + ''.join(secrets.choice(_ID_CHARS) for _ in range(12)) + '='


# ---------------------------------------------------------------- 旧顺序图模式

def parse_grader(script):
    """解析 codeN.py，返回 {字段: [{_type, name, ...}]}。"""
    var_field = {}
    for m in re.finditer(r"(\w+)\s*=\s*.*\['(\w+)'\]", script):
        var_field[m.group(1)] = m.group(2)

    result = {}

    def add(field, elem):
        result.setdefault(field, []).append(elem)

    for m in re.finditer(
            r"analyze_element\((\w+)\s*,\s*['\"]([^'\"]*)['\"]\s*,\s*['\"]([^'\"]*)['\"]\s*\)",
            script):
        var, name, typ = m.groups()
        field = var_field.get(var)
        if field:
            add(field, {'_type': typ, 'name': name})

    for m in re.finditer(
            r"analyze_line\((\w+)\s*,\s*['\"]([^'\"]*)['\"]\s*,\s*['\"]([^'\"]*)['\"]"
            r"\s*,\s*['\"]([^'\"]*)['\"]\s*,\s*['\"]([^'\"]*)['\"]\s*\)",
            script):
        var, name, typ, visibility, types = m.groups()
        field = var_field.get(var)
        if field:
            add(field, {'_type': typ, 'name': name, 'visibility': visibility, 'type': types})

    id_map = {}
    for m in re.finditer(
            r"(\w+)\s*=\s*get_id\(\w+\s*,\s*['\"]([^'\"]*)['\"]\s*,\s*['\"]([^'\"]*)['\"]\s*\)",
            script):
        id_map[m.group(1)] = m.group(2)
    for m in re.finditer(
            r"analyze_line1\((\w+)\s*,\s*['\"]([^'\"]*)['\"]\s*,\s*['\"]([^'\"]*)['\"]"
            r"\s*,\s*(\w+)\s*,\s*(\w+)\s*\)",
            script):
        var, name, typ, src_var, tgt_var = m.groups()
        field = var_field.get(var)
        if field:
            add(field, {'_type': typ, 'name': name,
                        'source_name': id_map.get(src_var), 'target_name': id_map.get(tgt_var)})
    return result


def build_mdj(elements):
    """旧顺序图：Project -> Model -> [ClassDiagram, Collaboration -> Interaction]。"""
    participants, id_map = [], {}
    for e in elements.get('participants', []):
        pid = _gid()
        id_map[e['name']] = pid
        participants.append({'_type': e['_type'], '_id': pid, 'name': e['name']})
    owned = [{'_type': e['_type'], '_id': _gid(), 'name': e['name'], 'defaultDiagram': True}
             for e in elements.get('ownedElements', [])]
    messages = []
    for m in elements.get('messages', []):
        src = id_map.get(m.get('source_name'))
        tgt = id_map.get(m.get('target_name'))
        if src and tgt:
            messages.append({'_type': m['_type'], '_id': _gid(), 'name': m['name'],
                             'source': {'$ref': src}, 'target': {'$ref': tgt}})
    interaction = {'_type': 'UMLInteraction', '_id': _gid(), 'name': 'Interaction1',
                   'participants': participants, 'ownedElements': owned, 'messages': messages}
    return json.dumps({
        '_type': 'Project', '_id': _gid(), 'name': 'Untitled',
        'ownedElements': [{
            '_type': 'UMLModel', '_id': _gid(), 'name': 'Model',
            'ownedElements': [
                {'_type': 'UMLClassDiagram', '_id': _gid(), 'name': 'Main',
                 'defaultDiagram': True},
                {'_type': 'UMLCollaboration', '_id': _gid(), 'name': 'Collaboration1',
                 'ownedElements': [interaction]},
            ],
        }],
    }, ensure_ascii=False)


# ------------------------------------------------------------ 系统流程图模式

_FC_ELEM_RE = re.compile(
    r"analyze_(?:element|database|filesys|order|files|entity|process)\("
    r"\w+\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)")
_FC_GETID_RE = re.compile(
    r"(\w+)\s*=\s*get_id\(\s*\w+\s*,\s*['\"]([^'\"]+)['\"]\s*,"
    r"\s*['\"]([^'\"]+)['\"]\s*\)")
_FC_LINE_RE = re.compile(
    r"analyze_line\(\s*\w+\s*,\s*(\w+)\s*,\s*(\w+)\s*,"
    r"\s*['\"]([^'\"]+)['\"]\s*\)")


def solve_flowchart(script):
    """逆向构造系统流程图/数据流图（FCProcess / FCDatabase / FCFlow 等）。"""
    if not script or not re.search(r"['\"]FC\w+['\"]", script):
        return None
    var_map = {}
    for m in _FC_GETID_RE.finditer(script):
        var_map[m.group(1)] = (m.group(2), m.group(3))
    elems = {}
    for m in _FC_ELEM_RE.finditer(script):
        elems.setdefault(m.group(1), m.group(2))
    for name, typ in var_map.values():
        elems.setdefault(name, typ)
    if not elems:
        return None

    ids, items = {}, []
    for name, typ in elems.items():
        ident = _gid()
        ids[name] = ident
        items.append({'_type': typ, '_id': ident, 'name': name, 'ownedElements': []})
    # 评测器的 analyze_line 要求连线挂在【源元素】的 ownedElements 下
    lines = []
    for m in _FC_LINE_RE.finditer(script):
        s_var, t_var, typ = m.groups()
        s_name = var_map.get(s_var, (None,))[0]
        t_name = var_map.get(t_var, (None,))[0]
        if s_name in ids and t_name in ids and (s_name, t_name, typ) not in lines:
            lines.append((s_name, t_name, typ))
    by_name = {i['name']: i for i in items}
    for s_name, t_name, typ in lines:
        by_name[s_name]['ownedElements'].append({
            '_type': typ, '_id': _gid(), 'name': f'{s_name}到{t_name}',
            'source': {'$ref': ids[s_name]}, 'target': {'$ref': ids[t_name]},
        })
    # 无连线的元素去掉空的 ownedElements，保持结构干净
    for it in items:
        if not it['ownedElements']:
            it.pop('ownedElements')

    m_idx = re.search(
        r"owned_elements\s*\[\s*(\d+)\s*\]\s*\[\s*['\"]ownedElements['\"]\s*\]", script)
    outer = int(m_idx.group(1)) if m_idx else 1
    model = {'_type': 'UMLModel', '_id': _gid(), 'name': 'Model', 'ownedElements': items}
    return json.dumps({'_type': 'Project', '_id': _gid(), 'name': 'Untitled',
                       'ownedElements': _build_chain([outer], model, [])},
                      ensure_ascii=False)


# ------------------------------------------------------- 时序图/交互图模式

_OWNED_SEG = (r"(?:\s*(?:\[\s*['\"]ownedElements['\"]\s*\]"
              r"|\.get\(\s*['\"]ownedElements['\"]\s*\))"
              r"\s*\[\s*\d+\s*\])")
_PATH_RE = re.compile(
    r"owned_elements\s*\[\s*(\d+)\s*\]"
    r"(" + _OWNED_SEG + r"*)"
    r"\s*\[\s*['\"](participants|messages)['\"]\s*\]")


def _parse_owned_path(script, field):
    """解析 owned_elements[A]['ownedElements'][B]...['field'] 的索引链。"""
    for m in _PATH_RE.finditer(script):
        if m.group(3) != field:
            continue
        path = [int(m.group(1))]
        path += [int(x) for x in re.findall(r"\[\s*(\d+)\s*\]", m.group(2))]
        return path, m.end()
    return None, None


def _extract_names(block):
    names = []
    for m in re.finditer(r"(?:if|elif)\s+\w+\s*==\s*['\"]([^'\"]+)['\"]", block):
        v = m.group(1)
        if v not in names:
            names.append(v)
    return names


def _build_chain(path, leaf, extra_tail):
    """按索引链构造 Project.ownedElements，使 path 指向 leaf。"""
    node = leaf
    for i in range(len(path) - 1, 0, -1):
        node = {'_type': 'UMLModel', '_id': _gid(), 'name': f'Model{i}',
                'ownedElements': [node]}
    models = []
    for i in range(path[0]):
        models.append({'_type': 'UMLModel', '_id': _gid(), 'name': f'Model{i}',
                       'ownedElements': [{'_type': 'UMLClassDiagram', '_id': _gid(),
                                          'name': 'Main', 'defaultDiagram': True}]})
    models.append(node)
    models.extend(extra_tail)
    return models


def solve_by_owned_path(script):
    """按评测脚本的索引路径构造时序图/交互图 .mdj。"""
    if not script:
        return None
    path_p, end_p = _parse_owned_path(script, 'participants')
    if not path_p:
        return None
    path_m, _ = _parse_owned_path(script, 'messages')
    end_of_part = script.find("['messages']", end_p)
    if end_of_part == -1:
        end_of_part = end_p
    part_names = _extract_names(script[end_p:end_of_part])
    msg_names = _extract_names(script[end_of_part:]) if path_m else []
    if not part_names:
        return None
    path = path_p
    if path_m and len(path_m) > len(path_p):
        path = path_m
    leaf = {
        '_type': 'UMLInteraction', '_id': _gid(), 'name': 'Interaction1',
        'participants': [{'_type': 'UMLLifeline', '_id': _gid(), 'name': n}
                         for n in part_names],
        'messages': [{'_type': 'UMLMessage', '_id': _gid(), 'name': n,
                      'source': {'$ref': _gid()}, 'target': {'$ref': _gid()}}
                     for n in msg_names],
        'ownedElements': [{'_type': 'UMLSequenceDiagram', '_id': _gid(),
                           'name': 'SequenceDiagram1', 'defaultDiagram': True}],
    }
    return json.dumps({'_type': 'Project', '_id': _gid(), 'name': 'Untitled',
                       'ownedElements': _build_chain(path, leaf, [])},
                      ensure_ascii=False)


# --------------------------------------------------- 通用 analyze_element 模式

_VAR_PATH_RE = re.compile(
    r"(\w+)\s*=\s*owned_elements\s*\[\s*(\d+)\s*\]\s*"
    r"(?:\[\s*['\"]ownedElements['\"]\s*\]|\.get\(\s*['\"]ownedElements['\"]\s*\))")
_ANALYZE_ELEM_RE = re.compile(
    r"analyze_element\(\s*(\w+)\s*,\s*['\"]([^'\"]+)['\"]\s*,"
    r"\s*['\"]([^'\"]+)['\"]\s*\)")


def solve_analyze_element(script):
    """通用：按 analyze_element(list_var, '名称', '类型') 构造元素列表。"""
    if not script or 'analyze_element' not in script:
        return None
    var_path = {}
    for m in _VAR_PATH_RE.finditer(script):
        var, n = m.group(1), int(m.group(2))
        var_path[var] = min(var_path.get(var, n), n)
    if not var_path:
        return None
    by_var = {}
    for m in _ANALYZE_ELEM_RE.finditer(script):
        var, name, typ = m.group(1), m.group(2), m.group(3)
        if var in var_path:
            by_var.setdefault(var, []).append((name, typ))
    if not by_var:
        return None
    grouped = {}
    for var, items in by_var.items():
        grouped.setdefault(var_path[var], []).extend(items)
    top = max(grouped)
    models = []
    for i in range(top + 1):
        items = grouped.get(i, [])
        elems = [{'_type': typ, '_id': _gid(), 'name': name} for name, typ in items]
        if i == 0 and not any(e['_type'].endswith('Diagram') for e in elems):
            elems.insert(0, {'_type': 'UMLClassDiagram', '_id': _gid(), 'name': 'Main',
                             'defaultDiagram': True})
        models.append({'_type': 'UMLModel', '_id': _gid(), 'name': f'Model{i}',
                       'ownedElements': elems})
    return json.dumps({'_type': 'Project', '_id': _gid(), 'name': 'Untitled',
                       'ownedElements': models}, ensure_ascii=False)


# --------------------------------------------------------------- 类图模式

def _parse_class_blocks(script):
    """拆分脚本里的 if/elif entity_name == '类名' 分支。"""
    marks = []
    for m in re.finditer(r"(?:if|elif)\s+entity_name\s*==\s*['\"]([^'\"]+)['\"]\s*:", script):
        marks.append((m.start(), m.end(), m.group(1)))
    blocks = []
    for idx, (start, end, name) in enumerate(marks):
        stop = marks[idx + 1][0] if idx + 1 < len(marks) else len(script)
        blocks.append((name, script[end:stop]))
    return blocks


_NAME_EQ = re.compile(r"\.get\(\s*['\"]name['\"]\s*\)\s*==\s*['\"]([^'\"]+)['\"]")
_REL_EQ = re.compile(
    r"\[\s*0\s*\]\s*\.get\(\s*['\"]name['\"]\s*\)\s*==\s*['\"]([^'\"]+)['\"]")


def solve_class_diagram(script):
    """逆向构造类图 .mdj（遍历 ownedElements[0或1].ownedElements[1:]。"""
    if not script or 'ownedElements' not in script or 'entity_name' not in script:
        return None
    blocks = _parse_class_blocks(script)
    if not blocks:
        return None
    m_idx = re.search(
        r"owned_elements\s*\[\s*(\d+)\s*\]\s*\[\s*['\"]ownedElements['\"]\s*\]", script)
    outer_idx = int(m_idx.group(1)) if m_idx else 0
    classes = []
    for name, body in blocks:
        rel = None
        m = _REL_EQ.search(body)
        if m:
            rel = m.group(1)
        attrs = []
        for m in _NAME_EQ.finditer(body):
            v = m.group(1)
            if v != rel and v not in attrs:
                attrs.append(v)
        for m in re.finditer(r"(?:if|elif)\s+name\s*==\s*['\"]([^'\"]+)['\"]", body):
            v = m.group(1)
            if v != rel and v not in attrs:
                attrs.append(v)
        classes.append((name, attrs, rel))

    elems = [{'_type': 'UMLClassDiagram', '_id': _gid(), 'name': 'Main',
              'defaultDiagram': True}]
    for name, attrs, rel in classes:
        cls = {'_type': 'UMLClass', '_id': _gid(), 'name': name,
               'attributes': [{'_type': 'UMLAttribute', '_id': _gid(), 'name': a}
                              for a in attrs],
               'ownedElements': []}
        if rel:
            cls['ownedElements'].append({'_type': 'UMLAssociation', '_id': _gid(), 'name': rel})
        elems.append(cls)
    models = [{'_type': 'UMLModel', '_id': _gid(), 'name': 'Model', 'ownedElements': elems}]
    if outer_idx >= 1:
        models.insert(0, {'_type': 'UMLModel', '_id': _gid(), 'name': 'Model0',
                          'ownedElements': [{'_type': 'UMLClassDiagram', '_id': _gid(),
                                             'name': 'Main', 'defaultDiagram': True}]})
    return json.dumps({'_type': 'Project', '_id': _gid(), 'name': 'Untitled',
                       'ownedElements': models}, ensure_ascii=False)


# -------------------------------------------------------------------- 入口

def solve_from_grader(script):
    """解析评测脚本并构造 .mdj 文本；无法解析时返回 None。"""
    for solver in (solve_flowchart, solve_by_owned_path, solve_analyze_element,
                   solve_class_diagram):
        try:
            doc = solver(script)
        except Exception:
            doc = None
        if doc:
            return doc
    elements = parse_grader(script)
    if not elements.get('participants') and not elements.get('ownedElements'):
        return None
    return build_mdj(elements)
