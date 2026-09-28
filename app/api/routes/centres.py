import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_admin
from app.database import get_db
from app.models.diagnostics import DiagnosticCentre
from app.schemas.diagnostics import CentreCreate, CentreOut, CentreUpdate

router = APIRouter(prefix="/centres", tags=["diagnostic-centres"])


def _get_centre_or_404(centre_id: uuid.UUID, db: Session) -> DiagnosticCentre:
    centre = (
        db.query(DiagnosticCentre)
        .options(joinedload(DiagnosticCentre.tests))
        .filter(DiagnosticCentre.id == centre_id)
        .first()
    )
    if centre is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Diagnostic centre not found"
        )
    return centre


@router.post("/", response_model=CentreOut, status_code=status.HTTP_201_CREATED)
def create_centre(
    payload: CentreCreate,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    centre = DiagnosticCentre(name=payload.name, location=payload.location)
    db.add(centre)
    db.commit()
    db.refresh(centre)
    return centre


@router.get("/", response_model=list[CentreOut])
def list_centres(db: Session = Depends(get_db)):
    return db.query(DiagnosticCentre).options(joinedload(DiagnosticCentre.tests)).all()


@router.get("/{centre_id}", response_model=CentreOut)
def get_centre(centre_id: uuid.UUID, db: Session = Depends(get_db)):
    return _get_centre_or_404(centre_id, db)


@router.patch("/{centre_id}", response_model=CentreOut)
def update_centre(
    centre_id: uuid.UUID,
    payload: CentreUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    centre = _get_centre_or_404(centre_id, db)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(centre, field, value)
    db.commit()
    db.refresh(centre)
    return centre
