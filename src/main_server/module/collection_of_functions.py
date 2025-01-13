import sympy


def update_dict(d, u):
    for key, value in u.items():
        if isinstance(value, dict) and key in d and isinstance(d[key], dict):
            update_dict(d[key], value)  # 재귀 호출로 내부 dict까지 업데이트
        else:
            d[key] = value  # 내부 dict가 없거나 값이 중첩되지 않은 경우 업데이트
    return d


def flatten_dict(d, parent_key=""):
    b = {}
    for key, value in d.items():
        new_key = f"{parent_key}_{key}" if parent_key else key  # 부모 키가 있으면 연결
        if isinstance(value, dict):
            # 재귀 호출로 중첩된 딕셔너리를 처리
            b.update(flatten_dict(value, new_key))
        else:
            # 값이 딕셔너리가 아니면 추가
            b[new_key] = value
    return b


def json_default(obj):
    if isinstance(obj, sympy.core.numbers.Float):
        return float(obj)
    print(obj, type(obj))
    raise TypeError


# 각도 찾기
def search_theta(theta: float):
    if 0 <= theta < 45:
        return_theta = 0
    elif 45 <= theta < 135:
        return_theta = 90
    elif 135 <= theta < 225:
        return_theta = 180
    elif 225 <= theta < 315:
        return_theta = 270
    else:
        return_theta = 0
    return return_theta