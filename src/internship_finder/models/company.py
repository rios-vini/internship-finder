from pydantic import BaseModel


class Company(BaseModel):
    name: str
    ats: str
    slug: str
    url: str
