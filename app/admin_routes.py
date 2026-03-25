from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import User, Doctor, Appointment
from app.auth import require_role
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/admin", tags=["Admin"])


# ─── Schemas (inline, no need to pollute schemas.py) ─────

class DoctorCreate(BaseModel):
    name: str
    specialization: Optional[str] = None
    experience_years: Optional[int] = 0


# ─── System stats ─────────────────────────────────────────

@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN"))
):
    total_users = db.query(User).count()
    total_patients = db.query(User).filter(User.role == "PATIENT").count()
    total_doctors = db.query(User).filter(User.role == "DOCTOR").count()
    total_appointments = db.query(Appointment).count()
    pending = db.query(Appointment).filter(Appointment.status == "pending").count()
    confirmed = db.query(Appointment).filter(Appointment.status == "confirmed").count()
    cancelled = db.query(Appointment).filter(Appointment.status == "cancelled").count()
    completed = db.query(Appointment).filter(Appointment.status == "completed").count()

    return {
        "total_users": total_users,
        "total_patients": total_patients,
        "total_doctors": total_doctors,
        "total_appointments": total_appointments,
        "appointments_by_status": {
            "pending": pending,
            "confirmed": confirmed,
            "cancelled": cancelled,
            "completed": completed
        }
    }


# ─── All users ────────────────────────────────────────────

@router.get("/users")
def get_all_users(
    role: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN"))
):
    query = db.query(User)
    if role:
        query = query.filter(User.role == role.upper())
    users = query.order_by(User.id.desc()).all()

    return [
        {
            "user_id": u.id,
            "name": u.name,
            "email": u.email,
            "phone": u.phone,
            "role": u.role,
            "appointment_count": db.query(Appointment).filter(
                Appointment.patient_id == u.id
            ).count() if u.role == "PATIENT" else None
        }
        for u in users
    ]


# ─── All appointments (across all doctors) ───────────────

@router.get("/appointments")
def get_all_appointments(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN"))
):
    query = db.query(Appointment)
    if status_filter:
        query = query.filter(Appointment.status == status_filter)
    appts = query.order_by(Appointment.date_time.desc()).all()

    result = []
    for a in appts:
        patient = db.query(User).filter(User.id == a.patient_id).first()
        doctor = db.query(Doctor).filter(Doctor.id == a.doctor_id).first()
        result.append({
            "appointment_id": a.id,
            "patient_name": patient.name if patient else "Unknown",
            "patient_email": patient.email if patient else "",
            "doctor_name": doctor.name if doctor else "Unknown",
            "doctor_specialization": doctor.specialization if doctor else "",
            "date_time": a.date_time,
            "reason": a.reason,
            "status": a.status
        })

    return result


# ─── All doctors ──────────────────────────────────────────

@router.get("/doctors")
def get_all_doctors(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN"))
):
    doctors = db.query(Doctor).all()
    result = []
    for d in doctors:
        user = db.query(User).filter(User.id == d.user_id).first() if d.user_id else None
        appt_count = db.query(Appointment).filter(Appointment.doctor_id == d.id).count()
        result.append({
            "doctor_id": d.id,
            "user_id": d.user_id,
            "name": d.name,
            "email": user.email if user else None,
            "specialization": d.specialization,
            "experience_years": d.experience_years,
            "patients_count": d.patients_count,
            "appointment_count": appt_count
        })
    return result


# ─── Add doctor (admin manually creates a doctor profile) ─

@router.post("/doctors", status_code=201)
def add_doctor(
    data: DoctorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN"))
):
    doctor = Doctor(
        name=data.name,
        specialization=data.specialization,
        experience_years=data.experience_years or 0,
        patients_count=0,
        availability={}
    )
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    return {"message": "Doctor added successfully", "doctor_id": doctor.id}


# ─── Remove doctor ────────────────────────────────────────

@router.delete("/doctors/{doctor_id}")
def remove_doctor(
    doctor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN"))
):
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    # If linked to a user account, demote them to PATIENT
    if doctor.user_id:
        user = db.query(User).filter(User.id == doctor.user_id).first()
        if user:
            user.role = "PATIENT"

    db.delete(doctor)
    db.commit()
    return {"message": "Doctor removed successfully"}


# ─── Update doctor profile ────────────────────────────────

@router.put("/doctors/{doctor_id}")
def update_doctor(
    doctor_id: int,
    data: DoctorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN"))
):
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    doctor.name = data.name
    doctor.specialization = data.specialization
    doctor.experience_years = data.experience_years or 0
    db.commit()
    return {"message": "Doctor updated successfully"}