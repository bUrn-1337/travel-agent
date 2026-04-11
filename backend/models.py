from datetime import datetime
from uuid import uuid4
from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id         = Column(String, primary_key=True, default=lambda: str(uuid4()))
    google_id  = Column(String, unique=True, nullable=False)
    email      = Column(String, nullable=False)
    name       = Column(String, nullable=False)
    avatar_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    trips = relationship("SavedTrip", back_populates="user", cascade="all, delete-orphan")


class SavedTrip(Base):
    __tablename__ = "saved_trips"

    id               = Column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id          = Column(String, ForeignKey("users.id"), nullable=False)
    destination_id   = Column(String, nullable=False)
    destination_name = Column(String, nullable=False)
    destination_data = Column(JSON, nullable=False)   # full destination dict
    plan_markdown    = Column(Text, nullable=True)     # generated AI plan
    days             = Column(Integer, nullable=False, default=5)
    budget_per_day   = Column(Integer, nullable=False, default=2000)
    group_type       = Column(String, nullable=False, default="friends")
    vibes            = Column(JSON, default=list)
    photo_url        = Column(String, nullable=True)
    is_public        = Column(Boolean, default=False)
    created_at       = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="trips")

    def to_dict(self):
        return {
            "id":               self.id,
            "destination_id":   self.destination_id,
            "destination_name": self.destination_name,
            "destination_data": self.destination_data,
            "plan_markdown":    self.plan_markdown,
            "days":             self.days,
            "budget_per_day":   self.budget_per_day,
            "group_type":       self.group_type,
            "vibes":            self.vibes or [],
            "photo_url":        self.photo_url,
            "is_public":        self.is_public,
            "created_at":       self.created_at.isoformat(),
            "user":             {"name": self.user.name, "avatar_url": self.user.avatar_url} if self.user else None,
        }
