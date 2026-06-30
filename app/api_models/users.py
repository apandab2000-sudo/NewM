from pydantic import BaseModel, EmailStr, Field, ValidationError, field_serializer

class UserName(BaseModel):
    user_name: str

    @field_serializer("user_name")
    def clean_user_name(self, user_name: str):
        if not len(self.user_name.strip().split(" ")) == 2:
            raise ValidationError(
                "Not a valid user name. user name must contain white space separated first name and last name only without other special characters"
            )
        return user_name.strip().lower()
    
    @property
    def first_name(self) -> str:
        return self.clean_user_name(self.user_name).split(" ")[0]

    @property
    def last_name(self) -> str:
        return self.clean_user_name(self.user_name).split(" ")[1]

    @property
    def email_id(self) -> str:
        cleaned_user_name = self.clean_user_name(self.user_name)
        cleaned_user_name = cleaned_user_name.split(" ")
        return f"{cleaned_user_name[0]}.{cleaned_user_name[1]}@eclerx.com"