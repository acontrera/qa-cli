import requests, base64, os
pat = os.environ['AZURE_DEVOPS_PAT']
token = base64.b64encode(f':{pat}'.encode()).decode()
headers = {'Authorization': f'Basic {token}'}
r = requests.get('https://dev.azure.com/SuraColombia/Gerencia_Tecnologia/_apis/wit/workitemtypes/Bug/fields?api-version=7.1', headers=headers)
for f in r.json().get('value', []):
    if 'sever' in f['name'].lower() or 'sever' in f['referenceName'].lower():
        print(f['referenceName'], '-', f['name'])
