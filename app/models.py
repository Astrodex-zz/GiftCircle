from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey, Boolean, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def utcnow(): return datetime.now(timezone.utc).replace(tzinfo=None)

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__='users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320),unique=True,index=True)
    name: Mapped[str] = mapped_column(String(100),default='')
    notify_email: Mapped[bool] = mapped_column(Boolean,default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime,default=utcnow)
class UserProfileState(Base):
    __tablename__='user_profile_states'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'),primary_key=True)
    name_confirmed: Mapped[bool] = mapped_column(Boolean,default=True)

class AuthToken(Base):
    __tablename__='auth_tokens'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'),index=True)
    digest: Mapped[str] = mapped_column(String(64),unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    consumed_at: Mapped[datetime|None] = mapped_column(DateTime,nullable=True)
class Session(Base):
    __tablename__='sessions'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'),index=True)
    digest: Mapped[str] = mapped_column(String(64),unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
class Family(Base):
    __tablename__='families'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime,default=utcnow)
class Membership(Base):
    __tablename__='memberships'
    __table_args__=(UniqueConstraint('family_id','user_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey('families.id'),index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'),index=True)
class Invitation(Base):
    __tablename__='invitations'
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey('families.id'))
    email: Mapped[str] = mapped_column(String(320))
    digest: Mapped[str] = mapped_column(String(64),unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    accepted_at: Mapped[datetime|None] = mapped_column(DateTime,nullable=True)
class Exchange(Base):
    __tablename__='exchanges'
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey('families.id'),index=True)
    name: Mapped[str] = mapped_column(String(120))
    budget: Mapped[int] = mapped_column(Integer,default=50)
    exchange_date: Mapped[str] = mapped_column(String(10),default='')
    drawn_at: Mapped[datetime|None] = mapped_column(DateTime,nullable=True)
    reveal_at: Mapped[datetime|None] = mapped_column(DateTime,nullable=True)
class ExchangeInvitationText(Base):
    __tablename__='exchange_invitation_texts'
    exchange_id: Mapped[int] = mapped_column(ForeignKey('exchanges.id'),primary_key=True)
    message: Mapped[str] = mapped_column(Text,default='')

class Participant(Base):
    __tablename__='participants'
    __table_args__=(UniqueConstraint('exchange_id','user_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    exchange_id: Mapped[int] = mapped_column(ForeignKey('exchanges.id'),index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'),index=True)
class Exclusion(Base):
    __tablename__='exclusions'
    __table_args__=(UniqueConstraint('exchange_id','giver_id','recipient_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    exchange_id: Mapped[int] = mapped_column(ForeignKey('exchanges.id'),index=True)
    giver_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    recipient_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
class PreviousDrawRule(Base):
    __tablename__='previous_draw_rules'
    exchange_id: Mapped[int] = mapped_column(ForeignKey('exchanges.id'),primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey('exchanges.id'))
class Assignment(Base):
    __tablename__='assignments'
    __table_args__=(UniqueConstraint('exchange_id','giver_id'),UniqueConstraint('exchange_id','recipient_id'))
    id: Mapped[int] = mapped_column(primary_key=True)
    exchange_id: Mapped[int] = mapped_column(ForeignKey('exchanges.id'),index=True)
    giver_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    recipient_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
class Wish(Base):
    __tablename__='wishes'
    id: Mapped[int] = mapped_column(primary_key=True)
    exchange_id: Mapped[int] = mapped_column(ForeignKey('exchanges.id'),index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'),index=True)
    title: Mapped[str] = mapped_column(String(200))
    details: Mapped[str] = mapped_column(Text,default='')
    url: Mapped[str] = mapped_column(String(1500),default='')
    price: Mapped[str] = mapped_column(String(40),default='')
    reserved_by: Mapped[int|None] = mapped_column(ForeignKey('users.id'),nullable=True)
    purchased: Mapped[bool] = mapped_column(Boolean,default=False)
class Message(Base):
    __tablename__='messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    exchange_id: Mapped[int] = mapped_column(ForeignKey('exchanges.id'),index=True)
    assignment_id: Mapped[int|None] = mapped_column(ForeignKey('assignments.id'),nullable=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    kind: Mapped[str] = mapped_column(String(16),default='private')
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime,default=utcnow)
class Notification(Base):
    __tablename__='notifications'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'),index=True)
    exchange_id: Mapped[int] = mapped_column(ForeignKey('exchanges.id'))
    title: Mapped[str] = mapped_column(String(150))
    detail: Mapped[str] = mapped_column(String(500),default='')
    read_at: Mapped[datetime|None] = mapped_column(DateTime,nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime,default=utcnow)

class LoginAttempt(Base):
    __tablename__='login_attempts'
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64),index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime,default=utcnow)

class WishListState(Base):
    __tablename__='wish_list_states'
    exchange_id: Mapped[int] = mapped_column(ForeignKey('exchanges.id'),primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'),primary_key=True)
    finalised_at: Mapped[datetime|None] = mapped_column(DateTime,nullable=True)

class ReservationPolicy(Base):
    __tablename__='reservation_policies'
    exchange_id: Mapped[int] = mapped_column(ForeignKey('exchanges.id'),primary_key=True)
    mode: Mapped[str] = mapped_column(String(16),default='show')
class WishAvailability(Base):
    __tablename__='wish_availability'
    wish_id: Mapped[int] = mapped_column(ForeignKey('wishes.id'),primary_key=True)
    exchange_id: Mapped[int] = mapped_column(ForeignKey('exchanges.id'))

class RevealToken(Base):
    __tablename__='reveal_tokens'
    id: Mapped[int] = mapped_column(primary_key=True)
    exchange_id: Mapped[int] = mapped_column(ForeignKey('exchanges.id'),index=True)
    giver_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    digest: Mapped[str] = mapped_column(String(64),unique=True,index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
