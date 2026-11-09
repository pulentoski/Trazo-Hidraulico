"""Parámetros de diseño por proyecto.

Los valores por defecto salen del perfil de criterios del proyecto y de valores típicos de partida; todos
quedan marcados «no verificado» hasta que el proyectista los revise. El proyecto guarda solo su copia
editada (`project.design_params`).
"""
from sqlalchemy.orm import Session

from app.models import Project
from app.repositories import catalog as catalog_repo
from app.schemas.design import DesignParam, DesignParamUpdate
from app.services.criteria import criteria_map

CRITERIA = [  # key, etiqueta, unidad, límite, valor si el perfil no lo trae
    ("pressure_min", "Presión mínima de servicio", "m.c.a.", "min", 15.0),
    ("pressure_max", "Presión máxima estática", "m.c.a.", "max", 70.0),
    ("velocity_min", "Velocidad mínima", "m/s", "min", 0.3),
    ("velocity_max", "Velocidad máxima", "m/s", "max", 2.0),
    ("unit_headloss_max", "Pérdida unitaria máxima (cuello de botella)", "m/km", "max", 10.0),
    ("dn_min", "Diámetro nominal mínimo de red", "mm", "min", 75.0),
]
TYPICAL = "Valor típico de partida"
ESTANQUE = "Planilla ModeloEstanque (ingeniero hidráulico)"
EXTRAS = [
    DesignParam(key="dotacion", label="Dotación", group="demanda", value=150.0, unit="L/hab/día",
                source=f"{TYPICAL}; la planilla ModeloEstanque usa 160"),
    DesignParam(key="densidad", label="Densidad habitacional", group="demanda", value=5.0, unit="hab/viv",
                source=f"{ESTANQUE}, hoja Proyecc10-30HospChamp"),
    DesignParam(key="perdidas", label="Pérdidas", group="demanda", value=20.0, unit="%",
                source=f"{ESTANQUE}, hoja SimulaEST1 (la proyección usa 18 %)"),
    DesignParam(key="coef_max_diario", label="Coeficiente de máximo diario", group="demanda", value=1.5, unit="—",
                source=f"{ESTANQUE}"),
    DesignParam(key="coef_max_horario", label="Coeficiente de máximo horario", group="demanda", value=1.5, unit="—",
                source=f"{ESTANQUE}"),
    DesignParam(key="curva_modulacion", label="Curva de modulación horaria (0–23 h)", group="curva",
                value=[0.3, 0.2, 0.1, 0.1, 0.3, 0.5, 0.9, 1.5, 1.6, 1.5, 1.45, 1.35,
                       1.4, 1.4, 1.3, 1.1, 1.0, 0.9, 1.0, 1.2, 1.25, 1.2, 0.9, 0.5],
                unit="coef.", source=f"{ESTANQUE}, hoja CurvaMod (promedio 0,956, no normalizada)"),
]
EDITED = "Ingresado en el proyecto"


def defaults(session: Session, project: Project) -> list[DesignParam]:
    profile = catalog_repo.get_profile(session, project.design_profile_id)
    crit = criteria_map(profile.criteria if profile else None)
    src = f"Perfil «{profile.name}» v{profile.version}" if profile else TYPICAL
    verified = bool(profile and profile.verified)
    out = []
    for key, label, unit, bound, fallback in CRITERIA:
        v = (crit.get(key) or {}).get(bound)
        out.append(DesignParam(key=key, label=label, group="criterio", value=float(v if v is not None else fallback),
                               unit=unit, bound=bound, source=src if v is not None else TYPICAL,
                               verified=verified and v is not None))
    return out + [p.model_copy() for p in EXTRAS]


def effective(session: Session, project: Project) -> list[DesignParam]:
    base = {p.key: p for p in defaults(session, project)}
    for raw in project.design_params or []:
        p = DesignParam(**raw)
        if p.key in base:
            base[p.key] = p
    return list(base.values())


def param(params: list[DesignParam], key: str) -> DesignParam:
    return next(p for p in params if p.key == key)


def update(session: Session, project: Project, changes: list[DesignParamUpdate]) -> list[DesignParam]:
    current = {p.key: p for p in effective(session, project)}
    for ch in changes:
        if ch.key not in current:
            raise ValueError(f"Parámetro desconocido: {ch.key}")
        p = current[ch.key]
        if isinstance(p.value, list) != isinstance(ch.value, list):
            raise ValueError(f"{p.label}: tipo de valor inválido")
        if isinstance(ch.value, list) and len(ch.value) != len(p.value):
            raise ValueError(f"{p.label}: se esperan {len(p.value)} valores")
        changed = ch.value != p.value
        current[ch.key] = p.model_copy(update={
            "value": ch.value, "verified": ch.verified,
            "source": ch.source or (EDITED if changed else p.source),
        })
    defaults_by_key = {p.key: p for p in defaults(session, project)}
    project.design_params = [p.model_dump() for k, p in current.items() if p != defaults_by_key[k]] or None
    session.commit()
    return list(current.values())


def criteria_for(session: Session, project: Project) -> dict[str, dict]:
    """Criterios efectivos del proyecto en el formato de criteria_map: {key: {min|max: valor, ...}}."""
    out = {}
    for p in effective(session, project):
        if p.group == "criterio" and p.bound:
            out[p.key] = {"key": p.key, "label": p.label, p.bound: p.value, "unit": p.unit, "source": p.source,
                          "verified": p.verified}
    return out
