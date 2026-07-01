import os
from byteplussdkarkruntime import Ark

client = Ark(
    base_url='https://ark.ap-southeast.bytepluses.com/api/v3',
    api_key=os.getenv('ARK_API_KEY'),
)

response = client.responses.create(
    model="seed-2-0-lite-260228",
    input="hello", # Replace with your prompt
    # thinking={"type": "disabled"}, #  Manually disable deep thinking
)
print(response)