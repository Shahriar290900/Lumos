import { $ } from "./api.js";

$("#loginBtn").onclick = () => {
  localStorage.setItem("lumos_student", "demo_user");
  window.location.href = "/onboarding";
};

$("#demoLogin").onclick = () => {
  localStorage.setItem("lumos_student", "demo_user");
  window.location.href = "/onboarding";
};
