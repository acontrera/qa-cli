import requests, base64, os
pat = os.environ['AZURE_DEVOPS_PAT']
token = base64.b64encode(f':{pat}'.encode()).decode()
r = requests.get('https://dev.azure.com/SuraColombia/_apis/connectiondata?api-version=7.1', headers={'Authorization': f'Basic {token}'})
print(r.json().get('authenticatedUser', {}).get('providerDisplayName', 'desconocido'))
