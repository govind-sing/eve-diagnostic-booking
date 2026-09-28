import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.database import get_db
from app.models.diagnostics import DiagnosticCentre, DiagnosticTest
from app.schemas.diagnostics import TestCreate, TestOut, TestUpdate

router = APIRouter(tags=["diagnostic-tests"])


def _get_test_or_404(test_id: uuid.UUID, db: Session) -> DiagnosticTest:
    test = db.query(DiagnosticTest).filter(DiagnosticTest.id == test_id).first()
    if test is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Diagnostic test not found"
        )
    return test


@router.post(
    "/centres/{centre_id}/tests",
    response_model=TestOut,
    status_code=status.HTTP_201_CREATED,
)
def add_test_to_centre(
    centre_id: uuid.UUID,
    payload: TestCreate,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    centre = db.query(DiagnosticCentre).filter(DiagnosticCentre.id == centre_id).first()
    if centre is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Diagnostic centre not found"
        )

    test = DiagnosticTest(centre_id=centre.id, name=payload.name, price=payload.price)
    db.add(test)
    db.commit()
    db.refresh(test)
    return test


@router.get("/tests", response_model=list[TestOut])
def list_tests(centre_id: uuid.UUID | None = None, db: Session = Depends(get_db)):
    query = db.query(DiagnosticTest)
    if centre_id is not None:
        query = query.filter(DiagnosticTest.centre_id == centre_id)
    return query.all()


@router.get("/tests/{test_id}", response_model=TestOut)
def get_test(test_id: uuid.UUID, db: Session = Depends(get_db)):
    return _get_test_or_404(test_id, db)


@router.patch("/tests/{test_id}", response_model=TestOut)
def update_test(
    test_id: uuid.UUID,
    payload: TestUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    test = _get_test_or_404(test_id, db)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(test, field, value)
    db.commit()
    db.refresh(test)
    return test
