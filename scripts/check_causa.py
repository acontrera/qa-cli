import requests, base64, os, json
pat = os.environ['AZURE_DEVOPS_PAT']
token = base64.b64encode(f':{pat}'.encode()).decode()
headers = {'Authorization': f'Basic {token}'}
r = requests.get('https://dev.azure.com/SuraColombia/Gerencia_Tecnologia/_apis/wit/workitemtypes/Bug/fields/Custom.1ff41362-1763-4c5e-9804-ff32d104be24?api-version=7.1', headers=headers)
data = r.json()
for v in data.get('allowedValues', []):
    print(v)
