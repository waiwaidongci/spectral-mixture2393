from typing import Literal
from pydantic import BaseModel,Field,model_validator
class RunInput(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    library_id:int
    sample_ids:list[int]=Field(min_length=1,max_length=6)
    # Omitted entirely -> legacy independent noise with the historic sigma default.
    # "legacy" -> independent Gaussian sigma, explicitly chosen.
    # "blank" -> joint covariance frozen from a stored blank calibration.
    noise_mode:Literal["legacy","blank"]|None=None
    noise_sigma:float|None=Field(default=None,ge=0,le=.2,allow_inf_nan=False)
    calibration_id:int|None=None
    repeats:int=Field(default=80,ge=20,le=120)
    seed:int=Field(default=2026,ge=0,le=2147483647)
    @model_validator(mode="after")
    def noise_contract(self):
        provided=self.model_fields_set
        if self.noise_mode is None:
            if self.calibration_id is not None:raise ValueError("指定calibration_id时必须设置noise_mode为blank；未选择校准时保持旧版独立噪声")
            if self.noise_sigma is None:
                if "noise_sigma" in provided:raise ValueError("省略noise_mode时sigma不可为null；请显式选择空白校准")
                self.noise_sigma=.005
        elif self.noise_mode=="legacy":
            if self.noise_sigma is None:raise ValueError("旧版独立噪声需要明确sigma；若需联合噪声请选择空白校准")
            if self.calibration_id is not None:raise ValueError("旧版独立噪声不能携带calibration_id")
        else:
            if self.calibration_id is None:raise ValueError("空白联合噪声必须指定calibration_id")
            if self.noise_sigma is not None:raise ValueError("空白联合噪声不使用sigma，请将noise_sigma设为null或不提交")
        return self
