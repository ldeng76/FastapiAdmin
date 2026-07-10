import json, base64
js = '(() => JSON.stringify({initOK: window.__csInitOK, initError: window.__csInitError, trace: window.__rsTrace, testError: window.__dicomTestError}))()'
print(base64.b64encode(js.encode()).decode())
