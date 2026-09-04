import { $, api, fillOfferings } from "./api.js";

(async function init() {
  const { ok, body } = await api.curriculum();
  if (ok && body) fillOfferings($("#offering"), body.offerings);
  
  $("#startTutor").onclick = () => {
    localStorage.setItem("lumos_subject", $("#offering").value);
    window.location.href = "/chat";
  };
})();
