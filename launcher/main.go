package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"
	"unsafe"

	"github.com/jchv/go-webview2"
	"golang.org/x/sys/windows"
)

var (
	user32          = syscall.NewLazyDLL("user32.dll")
	procMessageBoxW = user32.NewProc("MessageBoxW")
	dwmapi          = syscall.NewLazyDLL("dwmapi.dll")
	procDwmSetWindowAttribute = dwmapi.NewProc("DwmSetWindowAttribute")
)

const (
	MB_OK            = 0x00000000
	MB_ICONERROR     = 0x00000010
	MB_ICONWARNING   = 0x00000030
	CREATE_NO_WINDOW = 0x08000000
	// DWMWA_USE_IMMERSIVE_DARK_MODE: 20 untuk Win10 1903+,
	// 19 untuk build lama. Border/titlebar ikut tema sistem.
	DWMWA_USE_IMMERSIVE_DARK_MODE_NEW = 20
	DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
)

func showMessage(title, text string, flags uint) {
	t, _ := syscall.UTF16PtrFromString(title)
	m, _ := syscall.UTF16PtrFromString(text)
	procMessageBoxW.Call(0, uintptr(unsafe.Pointer(m)), uintptr(unsafe.Pointer(t)), uintptr(flags))
}

func isServerRunning(url string) bool {
	client := http.Client{
		Timeout: 1 * time.Second,
	}
	resp, err := client.Get(url)
	if err == nil && resp.StatusCode == 200 {
		resp.Body.Close()
		return true
	}
	return false
}

func killPortOccupant(port int) {
	out, err := exec.Command("cmd", "/c", fmt.Sprintf("netstat -ano | findstr :%d | findstr LISTENING", port)).Output()
	if err != nil || len(out) == 0 {
		return
	}
	lines := strings.Split(string(out), "\n")
	for _, line := range lines {
		fields := strings.Fields(strings.TrimSpace(line))
		if len(fields) >= 5 {
			pid := fields[len(fields)-1]
			if pid != "0" && pid != "" {
				_ = exec.Command("taskkill", "/F", "/PID", pid).Run()
			}
		}
	}
}

func getLastLogLines(logPath string, maxLines int) string {
	b, err := os.ReadFile(logPath)
	if err != nil {
		return ""
	}
	lines := strings.Split(string(b), "\n")
	if len(lines) > maxLines {
		lines = lines[len(lines)-maxLines:]
	}
	return strings.Join(lines, "\n")
}

func acquireSingleInstance() (release func(), ok bool) {
	name, _ := windows.UTF16PtrFromString(`Local\TatapSingleInstance_v2`)
	h, err := windows.CreateMutex(nil, false, name)
	if err != nil {
		return func() {}, false
	}
	if windows.GetLastError() == windows.ERROR_ALREADY_EXISTS {
		windows.CloseHandle(h)
		return func() {}, false
	}
	return func() { windows.CloseHandle(h) }, true
}

func isSystemDarkMode() bool {
	// HKCU\...\Themes\Personalize\AppsUseLightTheme: 0 = dark, 1 = light.
	sub, _ := windows.UTF16PtrFromString(`Software\Microsoft\Windows\CurrentVersion\Themes\Personalize`)
	name, _ := windows.UTF16PtrFromString(`AppsUseLightTheme`)
	var k windows.Handle
	if err := windows.RegOpenKeyEx(windows.HKEY_CURRENT_USER, sub, 0, windows.KEY_READ, &k); err != nil {
		return true
	}
	defer windows.RegCloseKey(k)
	var typ, val uint32
	var n uint32 = 4
	if err := windows.RegQueryValueEx(k, name, nil, &typ, (*byte)(unsafe.Pointer(&val)), &n); err != nil {
		return true
	}
	return val == 0
}

func setDarkMode(hwnd uintptr, dark bool) {
	var v int32
	if dark {
		v = 1
	}
	pv := uintptr(unsafe.Pointer(&v))
	for _, attr := range []uintptr{DWMWA_USE_IMMERSIVE_DARK_MODE_NEW, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD} {
		r, _, _ := procDwmSetWindowAttribute.Call(hwnd, attr, pv, 4)
		if r == 0 {
			return
		}
	}
}

func runWebView(appURL, dataPath string) {
	w := webview2.NewWithOptions(webview2.WebViewOptions{
		Debug:     false,
		AutoFocus: true,
		DataPath:  dataPath,
		WindowOptions: webview2.WindowOptions{
			Title:  "Tatap - Nonton Santai di Lokal",
			Width:  1280,
			Height: 800,
			Center: true,
		},
	})
	if w == nil {
		showMessage("Tatap - Kesalahan",
			"WebView2 runtime tidak ditemukan.\n\nInstall Microsoft Edge WebView2 Runtime dari:\nhttps://developer.microsoft.com/microsoft-edge/webview2/",
			MB_OK|MB_ICONERROR)
		return
	}
	defer w.Destroy()
	setDarkMode(uintptr(w.Window()), isSystemDarkMode())
	w.Navigate(appURL)
	w.Run()
}

func main() {
	log.SetOutput(os.Stderr)

	release, single := acquireSingleInstance()
	if !single {
		return
	}
	defer release()

	exePath, err := os.Executable()
	if err != nil {
		exePath, _ = filepath.Abs(os.Args[0])
	}
	appDir := filepath.Dir(exePath)
	appURL := "http://127.0.0.1:8767"
	pingURL := appURL + "/api/ping"

	var pyCmd *exec.Cmd

	// 1. Cek apakah server sudah aktif dan sehat
	if !isServerRunning(pingURL) {
		// 2. Bersihkan zombie di port 8767
		killPortOccupant(8767)
		time.Sleep(300 * time.Millisecond)

		// 3. Tentukan path python.exe dan backend/main.py
		pythonExe := filepath.Join(appDir, "runtime", "python.exe")
		if _, err := os.Stat(pythonExe); os.IsNotExist(err) {
			p, errLook := exec.LookPath("python.exe")
			if errLook != nil {
				p, errLook = exec.LookPath("python")
			}
			if errLook != nil {
				showMessage("Tatap - Kesalahan", "Runtime Python tidak ditemukan di folder 'runtime\\python.exe' atau di sistem.", MB_OK|MB_ICONERROR)
				return
			}
			pythonExe = p
		}

		backendMain := filepath.Join(appDir, "backend", "main.py")
		if _, err := os.Stat(backendMain); os.IsNotExist(err) {
			showMessage("Tatap - Kesalahan", fmt.Sprintf("File backend tidak ditemukan:\n%s", backendMain), MB_OK|MB_ICONERROR)
			return
		}

		// Siapkan folder cache untuk log
		cacheDir := filepath.Join(appDir, "cache")
		_ = os.MkdirAll(cacheDir, 0755)
		logPath := filepath.Join(cacheDir, "server.log")
		logFile, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0644)

		// 4. Jalankan backend Python
		pyCmd = exec.Command(pythonExe, backendMain)
		pyCmd.Dir = appDir
		pyCmd.SysProcAttr = &syscall.SysProcAttr{
			HideWindow:    true,
			CreationFlags: CREATE_NO_WINDOW,
		}
		if err == nil {
			pyCmd.Stdout = logFile
			pyCmd.Stderr = logFile
			defer logFile.Close()
		}

		if err := pyCmd.Start(); err != nil {
			showMessage("Tatap - Gagal Start", fmt.Sprintf("Gagal menyalakan proses backend: %v", err), MB_OK|MB_ICONERROR)
			return
		}

		// 5. Polling hingga /api/ping merespons (maksimal 15 detik)
		ready := false
		for i := 0; i < 75; i++ {
			time.Sleep(200 * time.Millisecond)
			if isServerRunning(pingURL) {
				ready = true
				break
			}

			if pyCmd.Process != nil {
				var status uint32
				handle := syscall.Handle(pyCmd.Process.Pid)
				if syscall.GetExitCodeProcess(handle, &status) == nil && status != 259 { // 259 = STILL_ACTIVE
					break
				}
			}
		}

		if !ready {
			if pyCmd.Process != nil {
				_ = pyCmd.Process.Kill()
			}
			logSnippet := getLastLogLines(logPath, 10)
			msg := "Server backend tidak dapat berjalan atau gagal merespons dalam 15 detik."
			if strings.TrimSpace(logSnippet) != "" {
				msg += "\n\nLog Kesalahan Terakhir:\n" + logSnippet
			}
			showMessage("Tatap - Gagal Memulai", msg, MB_OK|MB_ICONERROR)
			return
		}
	}

	// 6. Window close -> kill backend yang kita spawn
	if pyCmd != nil && pyCmd.Process != nil {
		defer func() {
			_ = pyCmd.Process.Kill()
		}()
	}

	// 7. Jendela native WebView2
	dataPath := filepath.Join(appDir, "cache", "webview2-data")
	_ = os.MkdirAll(dataPath, 0755)
	runWebView(appURL, dataPath)
}
