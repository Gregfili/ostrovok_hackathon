import { execFile } from "node:child_process"

const url = "http://127.0.0.1:8080/"

if (process.platform === "win32") {
  execFile("cmd", ["/c", "start", "", url])
} else if (process.platform === "darwin") {
  execFile("open", [url])
} else {
  execFile("xdg-open", [url])
}
