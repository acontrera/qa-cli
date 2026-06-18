import requests, base64, os, json
pat = os.environ['AZURE_DEVOPS_PAT']
token = base64.b64encode(f':{pat}'.encode()).decode()
headers = {'Authorization': f'Basic {token}'}
campos = ['Custom.Bloqueante', 'Custom.Nivelprueba', 'Custom.Atributodecalidad', 'Custom.Etapadedescubrimiento', 'Custom.Origen']
for c in campos:
    r = requests.get(f'https://dev.azure.com/SuraColombia/Gerencia_Tecnologia/_apis/wit/workitemtypes/Bug/fields/{c}?api-version=7.1', headers=headers)
    data = r.json()
    vals = data.get('allowedValues', [])
    print(c, vals)
