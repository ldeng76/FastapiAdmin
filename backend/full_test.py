import json, base64
with open('token_tmp.txt') as f:
    token = f.read().strip()
js = '''
(async () => {
  try {
    const T = %s;
    localStorage.setItem("access_token", T);
    localStorage.setItem("refresh_token", T);
    localStorage.setItem("remember_me", "true");
    const app = document.querySelector("#app").__vue_app__;
    const pinia = app.config.globalProperties.$pinia;
    const userStore = pinia._s.get("userStore");
    userStore.accessToken = T; userStore.isLogin = true;
    await userStore.getUserInfo();
    const router = app.config.globalProperties.$router;
    await router.push({path:"/medical/patient/detail", query:{detail:"00040449", center:"ZHU"}});
    await new Promise(r=>setTimeout(r,2500));
    // 点影像Tab + DICOM按钮
    document.querySelectorAll(".el-tabs__item").forEach(t=>{if(t.textContent.includes("影像"))t.click();});
    await new Promise(r=>setTimeout(r,800));
    document.querySelectorAll("button").forEach(b=>{if(b.textContent.includes("查看 DICOM 影像"))b.click();});
    await new Promise(r=>setTimeout(r,9000));
    // 通过 cornerstone API 测翻层
    const vp = window.__cv;
    let scrollResult = "no viewport hook";
    if(vp){
      const before = vp.getCurrentImageIdIndex();
      // 翻到第 100 层
      const imageIds = vp.getImageIds?.() || [];
      if(imageIds.length > 100){
        await vp.setStack(imageIds, 100);
        await new Promise(r=>setTimeout(r,3000));
      }
      const after = vp.getCurrentImageIdIndex();
      scrollResult = "before="+before+" after="+after+" total="+imageIds.length;
    }
    const overlay = document.querySelector(".viewport-overlay");
    const dicom = performance.getEntriesByType("resource").filter(e=>e.name.includes("dicom/instances"));
    return JSON.stringify({
      scrollResult,
      overlay: overlay?overlay.innerText.replace(/\s+/g," ").trim().slice(0,180):"none",
      dicomReqs: dicom.length,
      dicomStatus: [...new Set(dicom.map(e=>e.responseStatus))],
    });
  } catch(e){ return "ERR "+e.message; }
})()
''' % json.dumps(token)
print(base64.b64encode(js.encode()).decode())
