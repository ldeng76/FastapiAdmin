import json, base64
js = '''
(() => {
  return JSON.stringify({
    testImage: window.__dicomTestImage ? {rows: window.__dicomTestImage.rows, cols: window.__dicomTestImage.columns} : null,
    testError: window.__dicomTestError ? (window.__dicomTestError.message||String(window.__dicomTestError)).slice(0,250) : null,
    setStackError: window.__dicomSetStackError ? (window.__dicomSetStackError.message||String(window.__dicomSetStackError)).slice(0,250) : null,
    done: window.__done,
    viewportExposed: !!window.__dicomViewport,
  });
})()
'''
print(base64.b64encode(js.encode()).decode())
