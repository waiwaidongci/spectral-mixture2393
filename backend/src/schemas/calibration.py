from pydantic import BaseModel,Field

class CalibrationInput(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    library_id:int
    source:str=Field(default="",max_length=160)
    readings:list[list[float]]=Field(min_length=1,max_length=200)

class CalibrationRederive(BaseModel):
    name:str=Field(min_length=2,max_length=120)

class CalibrationOutput(BaseModel):
    id:int
    library_id:int
    name:str
    source:str
    band_count:int
    rule_version:str
    rule_current:bool
    source_hash:str
    calibration_hash:str
    readings_count:int
    effective_measurements:int
    degrees_of_freedom:int
    noise_rms:float
    condition_number:float
    derived_from_id:int|None
    owner:str
    created_at:str
    readings:list[list[float]]
    estimate:dict
