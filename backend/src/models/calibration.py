from sqlalchemy import String,Text,JSON,ForeignKey,Double,Integer,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from ..config.database import Base
from ..utils.clock import now
class BlankCalibration(Base):
    __tablename__="blank_calibrations"
    __table_args__=(UniqueConstraint("library_id","name"),)
    id:Mapped[int]=mapped_column(primary_key=True)
    library_id:Mapped[int]=mapped_column(ForeignKey("spectral_libraries.id"))
    name:Mapped[str]=mapped_column(String(120))
    source:Mapped[str]=mapped_column(String(160),default="")
    readings:Mapped[list]=mapped_column(JSON)
    band_count:Mapped[int]
    rule_version:Mapped[str]=mapped_column(String(64))
    source_hash:Mapped[str]=mapped_column(String(64))
    calibration_hash:Mapped[str]=mapped_column(String(64),unique=True)
    estimate:Mapped[dict]=mapped_column(JSON)
    effective_measurements:Mapped[int]=mapped_column(Integer)
    degrees_of_freedom:Mapped[int]=mapped_column(Integer)
    noise_rms:Mapped[float]=mapped_column(Double)
    condition_number:Mapped[float]=mapped_column(Double)
    derived_from_id:Mapped[int|None]=mapped_column(ForeignKey("blank_calibrations.id"),nullable=True,default=None)
    owner:Mapped[str]=mapped_column(String(100))
    created_at:Mapped[str]=mapped_column(String(64),default=now)
