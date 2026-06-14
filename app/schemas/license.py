from pydantic import BaseModel

class LicenseOperationRequest(BaseModel):
    user_id: str
    sku_id: str

class LicenseOperationResponse(BaseModel):
    success: bool
    message: str
    user_id: str
    sku_id: str