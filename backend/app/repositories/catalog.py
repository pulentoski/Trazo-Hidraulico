from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CatalogPipe, DesignProfile
from app.validators.network_validator import CatalogIndex


def list_pipes(session: Session) -> list[CatalogPipe]:
    return list(session.scalars(select(CatalogPipe).order_by(CatalogPipe.material, CatalogPipe.pipe_class, CatalogPipe.dn)))


def catalog_index(session: Session) -> CatalogIndex:
    idx = CatalogIndex()
    for p in list_pipes(session):
        idx.ids.add(p.id)
        idx.materials.add(p.material)
        idx.combos.add((p.material, p.dn, p.pipe_class))
        idx.dns.add((p.material, p.dn))
    return idx


def list_profiles(session: Session) -> list[DesignProfile]:
    return list(session.scalars(select(DesignProfile).order_by(DesignProfile.id)))


def get_profile(session: Session, profile_id: int | None) -> DesignProfile | None:
    if profile_id is None:
        return None
    return session.get(DesignProfile, profile_id)


def default_profile(session: Session) -> DesignProfile | None:
    return session.scalars(select(DesignProfile).order_by(DesignProfile.id).limit(1)).first()
