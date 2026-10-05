package main

import (
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

var (
	user32          = syscall.NewLazyDLL("user32.dll")
	procMessageBoxW = user32.NewProc("MessageBoxW")
)

const (
	MB_OK            = 0x00000000
	MB_ICONERROR     = 0x00000010
	MB_ICONWARNING   = 0x00000030
	CREATE_NO_WINDOW = 0x08000000
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
	// Jalankan netstat untuk mencari PID yang memakai port
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

func findEdge() string {
	candidates := []string{
		os.Getenv("ProgramFiles(x86)") + `\Microsoft\Edge\Application\msedge.exe`,
		os.Getenv("ProgramFiles") + `\Microsoft\Edge\Application\msedge.exe`,
		os.Getenv("LocalAppData") + `\Microsoft\Edge\Application\msedge.exe`,
	}
	for _, c := range candidates {
		if c != "" {
			if _, err := os.Stat(c); err == nil {
				return c
			}
		}
	}
	if p, err := exec.LookPath("msedge.exe"); err == nil {
		return p
	}
	return ""
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

func openUI(appURL, appDir string) {
	edgePath := findEdge()
	if edgePath != "" {
		edgeArgs := []string{
			fmt.Sprintf("--app=%s", appURL),
			"--new-window",
		}
		cmd := exec.Command(edgePath, edgeArgs...)
		cmd.Dir = appDir
		if err := cmd.Start(); err == nil {
			return
		}
	}
	// Fallback ke browser default
	_ = exec.Command("cmd", "/c", "start", appURL).Start()
}

func main() {
	exePath, err := os.Executable()
	if err != nil {
		exePath, _ = filepath.Abs(os.Args[0])
	}
	appDir := filepath.Dir(exePath)
	appURL := "http://127.0.0.1:8767"
	pingURL := appURL + "/api/ping"

	// 1. Cek apakah server sudah aktif dan sehat
	if isServerRunning(pingURL) {
		openUI(appURL, appDir)
		return
	}

	// 2. Jika port 8767 sedang diduduki zombie process (tidak merespons ping), bersihkan dulu
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
	pyCmd := exec.Command(pythonExe, backendMain)
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

		// Cek apakah proses python mati di tengah jalan
		if pyCmd.Process != nil {
			// Menggunakan FindProcess atau cek status
			var status uint32
			handle := syscall.Handle(pyCmd.Process.Pid)
			if syscall.GetExitCodeProcess(handle, &status) == nil && status != 259 { // 259 = STILL_ACTIVE
				break
			}
		}
	}

	if !ready {
		logSnippet := getLastLogLines(logPath, 10)
		msg := "Server backend tidak dapat berjalan atau gagal merespons dalam 15 detik."
		if strings.TrimSpace(logSnippet) != "" {
			msg += "\n\nLog Kesalahan Terakhir:\n" + logSnippet
		}
		showMessage("Tatap - Gagal Memulai", msg, MB_OK|MB_ICONERROR)
		return
	}

	// 6. Buka jendela aplikasi UI
	openUI(appURL, appDir)
}
