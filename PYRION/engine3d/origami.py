"""PYRION Origami: operaciones de topologia sobre datos .mesh (sin dependencias).

El modelo de edicion admite triangulos y quads; para dibujar siempre se
triangula. Las operaciones retornan copias, nunca modifican su entrada.
"""
import copy
import math


def _validate(model):
    vertices = model.get("vertices")
    faces = model.get("faces")
    if not isinstance(vertices, list) or not isinstance(faces, list):
        raise ValueError("Se requiere una malla explicita con vertices y faces")
    if any(len(v) != 3 or not all(math.isfinite(float(x)) for x in v) for v in vertices):
        raise ValueError("Vertice invalido")
    for f in faces:
        if len(f) not in (3, 4) or len(set(f)) != len(f) or any(
                type(i) is not int or i < 0 or i >= len(vertices) for i in f):
            raise ValueError("Cara invalida")
    colors = model.get("face_colors")
    if colors is not None and len(colors) != len(faces):
        raise ValueError("face_colors debe coincidir con faces")


def triangulate(model):
    """Acepta triangulos/quads y devuelve triangles compatibles con renderer."""
    _validate(model)
    result = copy.deepcopy(model)
    faces, colors = [], []
    original_colors = result.get("face_colors")
    for n, f in enumerate(result["faces"]):
        sub = [list(f)] if len(f) == 3 else [[f[0], f[1], f[2]], [f[0], f[2], f[3]]]
        faces.extend(sub)
        if original_colors is not None:
            colors.extend([original_colors[n]] * len(sub))
    result["faces"] = faces
    if original_colors is not None:
        result["face_colors"] = colors
    result["topology"] = "triangles"
    result.pop("groups", None)  # rangos obsoletos tras editar conectividad
    return result


def split_face(model, face_index, vertex_a=None, vertex_b=None):
    """Divide un quad mediante diagonal entre dos vertices opuestos.

    No se crean vertices nuevos. Las caras triangulares ya son indivisibles
    por diagonal; para ellas se debe usar subdivide_face.
    """
    _validate(model)
    result = copy.deepcopy(model)
    face = result["faces"][face_index]
    if len(face) != 4:
        raise ValueError("Split por diagonal requiere un quad")
    if vertex_a is None and vertex_b is None:
        vertex_a, vertex_b = face[0], face[2]
    if {vertex_a, vertex_b} == {face[0], face[2]}:
        pair = [[face[0], face[1], face[2]], [face[0], face[2], face[3]]]
    elif {vertex_a, vertex_b} == {face[1], face[3]}:
        pair = [[face[1], face[2], face[3]], [face[1], face[3], face[0]]]
    else:
        raise ValueError("La diagonal debe unir vertices opuestos")
    result["faces"][face_index:face_index + 1] = pair
    if "face_colors" in result:
        color = result["face_colors"][face_index]
        result["face_colors"][face_index:face_index + 1] = [color, color]
    result.pop("groups", None)
    return result


def merge_vertices(model, keep_index, remove_index, tolerance=None):
    """Fusiona dos vertices y elimina caras colapsadas.

    tolerance opcional: distancia maxima para autorizar la fusion.
    No repara autointersecciones; probar visualmente el resultado.
    """
    _validate(model)
    result = copy.deepcopy(model)
    v = result["vertices"]
    if type(keep_index) is not int or type(remove_index) is not int or not (
            0 <= keep_index < len(v) and 0 <= remove_index < len(v)) or keep_index == remove_index:
        raise ValueError("Indices de vertices invalidos")
    distance = math.dist(v[keep_index], v[remove_index])
    if tolerance is not None and distance > tolerance:
        raise ValueError("Vertices demasiado alejados para fusionar")
    new_faces, new_colors = [], []
    for n, f in enumerate(result["faces"]):
        changed = [keep_index if i == remove_index else i for i in f]
        changed = [i - 1 if i > remove_index else i for i in changed]
        compact = []
        for index in changed:
            if not compact or compact[-1] != index:
                compact.append(index)
        if len(compact) > 1 and compact[0] == compact[-1]:
            compact.pop()
        if len(set(compact)) < 3:
            continue
        if len(set(compact)) != len(compact):
            raise ValueError("Fusion produce una cara no valida")
        new_faces.append(compact)
        if "face_colors" in result:
            new_colors.append(result["face_colors"][n])
    v.pop(remove_index)
    result["faces"] = new_faces
    if "face_colors" in result:
        result["face_colors"] = new_colors
    result.pop("groups", None)
    return result


def weld_nearby(model, tolerance=1e-5):
    """Fusiona vertices coincidentes o proximos; tolerancia en unidades de modelo."""
    if tolerance <= 0:
        raise ValueError("tolerance debe ser positiva")
    result = copy.deepcopy(model)
    _validate(result)
    i = 0
    while i < len(result["vertices"]):
        j = i + 1
        while j < len(result["vertices"]):
            if math.dist(result["vertices"][i], result["vertices"][j]) <= tolerance:
                result = merge_vertices(result, i, j)
            else:
                j += 1
        i += 1
    return result
