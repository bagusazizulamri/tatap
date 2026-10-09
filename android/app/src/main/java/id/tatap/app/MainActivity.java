package id.tatap.app;

import android.app.Activity;
import android.content.Context;
import android.os.Bundle;
import android.util.Log;
import android.view.KeyEvent;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.recyclerview.widget.GridLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.util.ArrayList;
import java.util.List;

public class MainActivity extends Activity {
    private static final String TAG = "TatapMain";

    private EditText etSearch;
    private ProgressBar pbLoading;
    private TextView tvSectionTitle, tvItemCount, tvStatusBadge, tvPageIndicator;
    private RecyclerView rvGrid;
    private AnimeAdapter adapter;

    private Button btnTabMusim, btnTabAiring, btnTabKatalog;
    private Button btnPrevPage, btnNextPage;
    private View layoutPagination;

    // State navigasi tampilan & paging
    private String currentView = "musim"; // "musim" | "airing" | "katalog" | "cari" | "genre" | "season_filter"
    private String currentSearchQuery = "";
    private String currentGenre = "";
    private String currentSeasonName = "";
    private int currentSeasonYear = 0;
    private int currentPage = 1;
    private int totalPages = 1;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        etSearch = findViewById(R.id.et_search);
        pbLoading = findViewById(R.id.pb_loading);
        tvSectionTitle = findViewById(R.id.tv_section_title);
        tvItemCount = findViewById(R.id.tv_item_count);
        tvStatusBadge = findViewById(R.id.tv_status_badge);
        tvPageIndicator = findViewById(R.id.tv_page_indicator);
        rvGrid = findViewById(R.id.rv_anime_grid);

        btnTabMusim = findViewById(R.id.btn_tab_musim);
        btnTabAiring = findViewById(R.id.btn_tab_airing);
        btnTabKatalog = findViewById(R.id.btn_tab_katalog);
        btnPrevPage = findViewById(R.id.btn_prev_page);
        btnNextPage = findViewById(R.id.btn_next_page);
        layoutPagination = findViewById(R.id.layout_pagination);

        rvGrid.setLayoutManager(new GridLayoutManager(this, 2));
        adapter = new AnimeAdapter(this);
        rvGrid.setAdapter(adapter);

        setupTabsAndListeners();

        // 1. Jalankan backend Python lokal
        startEmbeddedBackend();

        // 2. Tunggu backend siap lalu muat konten pertama
        waitForServerAndLoadCatalog(0);
    }

    private void setupTabsAndListeners() {
        etSearch.setOnEditorActionListener((v, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_SEARCH ||
                    (event != null && event.getKeyCode() == KeyEvent.KEYCODE_ENTER && event.getAction() == KeyEvent.ACTION_DOWN)) {
                hideKeyboard();
                String raw = etSearch.getText().toString().trim();
                if (!raw.isEmpty()) {
                    if (raw.startsWith(":") || raw.startsWith("/")) {
                        executeCommand(raw.substring(1).trim());
                    } else {
                        currentView = "cari";
                        currentSearchQuery = raw;
                        currentPage = 1;
                        updateTabButtons();
                        fetchData();
                    }
                }
                return true;
            }
            return false;
        });

        btnTabMusim.setOnClickListener(v -> switchView("musim"));
        btnTabAiring.setOnClickListener(v -> switchView("airing"));
        btnTabKatalog.setOnClickListener(v -> switchView("katalog"));

        btnPrevPage.setOnClickListener(v -> {
            if (currentPage > 1) {
                currentPage--;
                fetchData();
            }
        });

        btnNextPage.setOnClickListener(v -> {
            currentPage++;
            fetchData();
        });
    }

    private void executeCommand(String commandLine) {
        if (commandLine.isEmpty()) return;
        String[] parts = commandLine.split("\\s+");
        String cmd = parts[0].toLowerCase();
        String args = commandLine.length() > cmd.length() ? commandLine.substring(cmd.length()).trim() : "";

        switch (cmd) {
            case "help":
            case "bantuan":
            case "?":
                showCommandHelpDialog();
                break;

            case "musim":
                switchView("musim");
                Toast.makeText(this, "Beralih ke: Tayang Musim Ini", Toast.LENGTH_SHORT).show();
                break;

            case "season":
                if (!args.isEmpty()) {
                    handleSeasonFilterCommand(parts);
                } else {
                    switchView("musim");
                    Toast.makeText(this, "Beralih ke: Tayang Musim Ini (Gunakan :season <winter|spring|summer|fall> <tahun> untuk filter)", Toast.LENGTH_LONG).show();
                }
                break;

            case "airing":
            case "terbaru":
                switchView("airing");
                Toast.makeText(this, "Beralih ke: Masih Tayang", Toast.LENGTH_SHORT).show();
                break;

            case "katalog":
            case "catalog":
                switchView("katalog");
                Toast.makeText(this, "Beralih ke: Katalog Populer", Toast.LENGTH_SHORT).show();
                break;

            case "genre":
                if (args.isEmpty() || args.equalsIgnoreCase("list") || args.equalsIgnoreCase("--list")) {
                    showGenreSelectorDialog();
                } else {
                    setGenreFilter(args);
                }
                break;

            case "cari":
            case "search":
                if (!args.isEmpty()) {
                    currentView = "cari";
                    currentSearchQuery = args;
                    currentPage = 1;
                    updateTabButtons();
                    fetchData();
                } else {
                    Toast.makeText(this, "Gunakan: :cari <judul>", Toast.LENGTH_SHORT).show();
                }
                break;

            case "page":
            case "hal":
                try {
                    int p = Integer.parseInt(args);
                    if (p >= 1) {
                        currentPage = p;
                        fetchData();
                        Toast.makeText(this, "Menuju halaman " + p, Toast.LENGTH_SHORT).show();
                    }
                } catch (Exception e) {
                    Toast.makeText(this, "Gunakan: :page <nomor>", Toast.LENGTH_SHORT).show();
                }
                break;

            case "source":
            case "switch":
                switchDefaultSource(args);
                break;

            case "ping":
            case "status":
                checkBackendStatus();
                break;

            case "clear":
            case "reset":
                etSearch.setText("");
                currentGenre = "";
                currentSeasonName = "";
                currentSeasonYear = 0;
                switchView("musim");
                break;

            default:
                Toast.makeText(this, "Perintah tidak dikenal: :" + cmd + " (Ketik :help untuk bantuan)", Toast.LENGTH_LONG).show();
                break;
        }
    }

    private void handleSeasonFilterCommand(String[] parts) {
        // Format: :season <winter|spring|summer|fall> [tahun]
        if (parts.length >= 2) {
            String sName = parts[1].toLowerCase();
            if (!sName.matches("^(winter|spring|summer|fall)$")) {
                Toast.makeText(this, "Musim valid: winter, spring, summer, fall. Contoh: :season fall 2024", Toast.LENGTH_LONG).show();
                return;
            }
            int sYear = 2024;
            if (parts.length >= 3) {
                try {
                    sYear = Integer.parseInt(parts[2]);
                } catch (Exception ignored) {}
            }
            currentView = "season_filter";
            currentSeasonName = sName;
            currentSeasonYear = sYear;
            currentPage = 1;
            updateTabButtons();
            fetchData();
            Toast.makeText(this, "Filter Musim: " + sName.toUpperCase() + " " + sYear, Toast.LENGTH_SHORT).show();
        } else {
            Toast.makeText(this, "Format: :season <winter|spring|summer|fall> <tahun>", Toast.LENGTH_LONG).show();
        }
    }

    private void setGenreFilter(String genreSlugOrTitle) {
        currentView = "genre";
        currentGenre = genreSlugOrTitle.toLowerCase().trim().replace(" ", "-");
        currentPage = 1;
        updateTabButtons();
        fetchData();
        Toast.makeText(this, "Filter Genre: " + currentGenre.toUpperCase(), Toast.LENGTH_SHORT).show();
    }

    private void showGenreSelectorDialog() {
        new Thread(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL("http://127.0.0.1:8767/api/genres").openConnection();
                conn.setConnectTimeout(6000);
                BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) sb.append(line);
                reader.close();

                JSONObject res = new JSONObject(sb.toString());
                if (res.optBoolean("success")) {
                    JSONArray arr = res.getJSONObject("data").getJSONArray("list");
                    List<String> titles = new ArrayList<>();
                    List<String> slugs = new ArrayList<>();
                    for (int i = 0; i < arr.length(); i++) {
                        JSONObject g = arr.getJSONObject(i);
                        titles.add(g.optString("title", ""));
                        slugs.add(g.optString("slug", ""));
                    }
                    runOnUiThread(() -> {
                        String[] items = titles.toArray(new String[0]);
                        new android.app.AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
                                .setTitle("Pilih Genre Anime")
                                .setItems(items, (dialog, which) -> {
                                    setGenreFilter(slugs.get(which));
                                })
                                .setNegativeButton("Batal", (dialog, which) -> dialog.dismiss())
                                .show();
                    });
                }
            } catch (Exception e) {
                runOnUiThread(() -> {
                    // Fallback list genre populer jika offline
                    String[] fallback = new String[]{"Action", "Adventure", "Comedy", "Drama", "Fantasy", "Horror", "Mystery", "Romance", "Sci-Fi", "Slice of Life", "Sports", "Supernatural"};
                    new android.app.AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
                            .setTitle("Pilih Genre Anime (Default)")
                            .setItems(fallback, (dialog, which) -> {
                                setGenreFilter(fallback[which].toLowerCase().replace(" ", "-"));
                            })
                            .setNegativeButton("Batal", (dialog, which) -> dialog.dismiss())
                            .show();
                });
            }
        }).start();
    }

    private void showCommandHelpDialog() {
        new android.app.AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
                .setTitle("Terminal Perintah Tatap (:command)")
                .setMessage("Perintah yang tersedia:\n\n"
                        + "• :musim - Tampilkan anime musim ini\n"
                        + "• :season <winter|spring|summer|fall> [tahun] - Filter anime musim & tahun tertentu (misal: :season fall 2024)\n"
                        + "• :genre [nama] - Filter anime berdasarkan genre (ketik :genre tanpa parameter untuk memilih dari daftar popup)\n"
                        + "• :airing - Tampilkan anime sedang tayang\n"
                        + "• :katalog - Tampilkan seluruh katalog populer\n"
                        + "• :cari <judul> - Cari judul anime tertentu\n"
                        + "• :page <nomor> - Lompat langsung ke halaman tertentu\n"
                        + "• :source [hi|otaku] - Ganti sumber scraping (HiAnime / Otakudesu)\n"
                        + "• :status / :ping - Periksa kesehatan backend lokal\n"
                        + "• :clear - Reset kolom input & kembali ke awal\n"
                        + "• :help - Buka bantuan perintah ini")
                .setPositiveButton("Tutup", (dialog, which) -> dialog.dismiss())
                .show();
    }

    private void switchDefaultSource(String target) {
        String s = target.toLowerCase().trim();
        String newSrc;
        if (s.contains("otaku")) {
            newSrc = "otakudesu";
        } else if (s.contains("hi")) {
            newSrc = "hianime";
        } else {
            newSrc = "hianime";
        }

        new Thread(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL("http://127.0.0.1:8767/api/settings").openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setDoOutput(true);
                JSONObject body = new JSONObject();
                body.put("preferred_source", newSrc);
                conn.getOutputStream().write(body.toString().getBytes("UTF-8"));
                conn.getInputStream().close();
                runOnUiThread(() -> {
                    Toast.makeText(this, "Sumber default diubah ke: " + (newSrc.equals("otakudesu") ? "Otakudesu (Sub Indo)" : "HiAnime"), Toast.LENGTH_LONG).show();
                    fetchData();
                });
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(this, "Gagal mengubah sumber: " + e.getMessage(), Toast.LENGTH_SHORT).show());
            }
        }).start();
    }

    private void checkBackendStatus() {
        new Thread(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL("http://127.0.0.1:8767/api/ping").openConnection();
                conn.setConnectTimeout(2000);
                boolean ok = conn.getResponseCode() == 200;
                conn.disconnect();
                runOnUiThread(() -> {
                    Toast.makeText(this, "Status Backend: " + (ok ? "ONLINE (127.0.0.1:8767 OK)" : "OFFLINE"), Toast.LENGTH_SHORT).show();
                });
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(this, "Status Backend: ERROR (" + e.getMessage() + ")", Toast.LENGTH_SHORT).show());
            }
        }).start();
    }

    private void switchView(String targetView) {
        currentView = targetView;
        currentPage = 1;
        updateTabButtons();
        fetchData();
    }

    private void updateTabButtons() {
        btnTabMusim.setBackgroundColor("musim".equals(currentView) ? 0xFF0E7490 : 0xFF161A24);
        btnTabMusim.setTextColor("musim".equals(currentView) ? 0xFFFFFFFF : 0xFF8892B0);

        btnTabAiring.setBackgroundColor("airing".equals(currentView) ? 0xFF0E7490 : 0xFF161A24);
        btnTabAiring.setTextColor("airing".equals(currentView) ? 0xFFFFFFFF : 0xFF8892B0);

        btnTabKatalog.setBackgroundColor("katalog".equals(currentView) ? 0xFF0E7490 : 0xFF161A24);
        btnTabKatalog.setTextColor("katalog".equals(currentView) ? 0xFFFFFFFF : 0xFF8892B0);
    }

    private void hideKeyboard() {
        InputMethodManager imm = (InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE);
        if (imm != null) {
            imm.hideSoftInputFromWindow(etSearch.getWindowToken(), 0);
        }
    }

    private void startEmbeddedBackend() {
        new Thread(() -> {
            try {
                Log.d(TAG, "Mencoba menyalakan Chaquopy Python Runtime...");
                Class<?> pyClass = Class.forName("com.chaquo.python.Python");
                if (!(Boolean) pyClass.getMethod("isStarted").invoke(null)) {
                    Class<?> androidPlatform = Class.forName("com.chaquo.python.android.AndroidPlatform");
                    Object platform = androidPlatform.getConstructor(Context.class).newInstance(getApplicationContext());
                    pyClass.getMethod("start", Class.forName("com.chaquo.python.Platform")).invoke(null, platform);
                }
                Object pyInstance = pyClass.getMethod("getInstance").invoke(null);
                Object launcherMod = pyClass.getMethod("getModule", String.class).invoke(pyInstance, "server_launcher");
                String dataDir = getFilesDir().getAbsolutePath();
                Log.d(TAG, "Menjalankan server_launcher.py dengan dataDir=" + dataDir);
                launcherMod.getClass().getMethod("callAttr", String.class, Object[].class).invoke(launcherMod, "run_in_background", new Object[]{dataDir});
                Log.d(TAG, "server_launcher.run_in_background dipanggil dengan sukses.");
            } catch (Throwable t) {
                Log.e(TAG, "Error startEmbeddedBackend: " + t.getMessage(), t);
                runOnUiThread(() -> {
                    Toast.makeText(this, "Gagal start backend: " + t.getMessage(), Toast.LENGTH_LONG).show();
                });
            }
        }).start();
    }

    private void waitForServerAndLoadCatalog(final int attempt) {
        new Thread(() -> {
            boolean ready = false;
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL("http://127.0.0.1:8767/api/ping").openConnection();
                conn.setConnectTimeout(800);
                conn.setReadTimeout(800);
                ready = (conn.getResponseCode() == 200);
                conn.disconnect();
            } catch (Exception ignored) {}

            final boolean isReady = ready;
            if (isReady) {
                runOnUiThread(() -> {
                    tvStatusBadge.setText("LOCAL OK");
                    tvStatusBadge.setTextColor(0xFF10B981);
                    fetchData();
                });
            } else if (attempt < 45) { // Coba sampai ~22 detik
                runOnUiThread(() -> {
                    if (attempt % 5 == 0 && attempt > 0) {
                        tvStatusBadge.setText("INIT " + (attempt * 2) + "%");
                        tvStatusBadge.setTextColor(0xFFF59E0B);
                    }
                });
                try { Thread.sleep(500); } catch (Exception ignored) {}
                waitForServerAndLoadCatalog(attempt + 1);
            } else {
                runOnUiThread(() -> {
                    tvStatusBadge.setText("OFFLINE (TAP)");
                    tvStatusBadge.setTextColor(0xFFEF4444);
                    Toast.makeText(this, "Server lokal butuh waktu inisialisasi lebih lama. Ketuk badge status untuk mencoba ulang.", Toast.LENGTH_LONG).show();
                    // Klik badge status untuk retry
                    tvStatusBadge.setOnClickListener(v -> {
                        tvStatusBadge.setText("RETRYING...");
                        tvStatusBadge.setTextColor(0xFFF59E0B);
                        startEmbeddedBackend();
                        waitForServerAndLoadCatalog(0);
                    });
                    fetchData();
                });
            }
        }).start();
    }

    private void fetchData() {
        pbLoading.setVisibility(View.VISIBLE);
        tvPageIndicator.setText("Hal " + currentPage);
        btnPrevPage.setEnabled(currentPage > 1);

        String title;
        String endpoint;

        if ("musim".equals(currentView)) {
            title = "Tayang Musim Ini (Hal " + currentPage + ")";
            endpoint = "/api/seasonal?which=now&page=" + currentPage;
        } else if ("airing".equals(currentView)) {
            title = "Masih Tayang (Hal " + currentPage + ")";
            endpoint = "/api/seasonal?which=prev&page=" + currentPage;
        } else if ("katalog".equals(currentView)) {
            title = "Katalog Populer (Hal " + currentPage + ")";
            endpoint = "/api/catalog?page=" + currentPage;
        } else if ("genre".equals(currentView)) {
            title = "Genre: " + currentGenre.toUpperCase() + " (Hal " + currentPage + ")";
            endpoint = "/api/browse?genre=" + URLEncoder.encode(currentGenre) + "&page=" + currentPage;
        } else if ("season_filter".equals(currentView)) {
            title = "Musim: " + currentSeasonName.toUpperCase() + " " + currentSeasonYear + " (Hal " + currentPage + ")";
            endpoint = "/api/seasonal?season=" + URLEncoder.encode(currentSeasonName) + "&year=" + currentSeasonYear + "&page=" + currentPage;
        } else {
            title = "Hasil Pencarian: " + currentSearchQuery;
            endpoint = "/api/search?q=" + URLEncoder.encode(currentSearchQuery) + "&limit=24";
        }

        tvSectionTitle.setText(title);

        new Thread(() -> {
            try {
                String u = "http://127.0.0.1:8767" + endpoint;
                HttpURLConnection conn = (HttpURLConnection) new URL(u).openConnection();
                conn.setConnectTimeout(12000);
                conn.setReadTimeout(15000);
                BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) sb.append(line);
                reader.close();

                JSONObject res = new JSONObject(sb.toString());
                if (res.optBoolean("success")) {
                    JSONObject data = res.getJSONObject("data");
                    JSONArray arr = data.optJSONArray("results");
                    if (arr == null) arr = data.optJSONArray("items");
                    if (arr == null) arr = new JSONArray();

                    List<JSONObject> list = new ArrayList<>();
                    for (int i = 0; i < arr.length(); i++) {
                        list.add(arr.getJSONObject(i));
                    }

                    final int count = list.size();
                    runOnUiThread(() -> {
                        pbLoading.setVisibility(View.GONE);
                        tvItemCount.setText(count + " judul");
                        adapter.setData(list);
                        btnNextPage.setEnabled(count >= 10);
                        if (rvGrid != null) rvGrid.scrollToPosition(0);
                    });
                } else {
                    final String err = res.optString("error", "gagal memuat data");
                    runOnUiThread(() -> {
                        pbLoading.setVisibility(View.GONE);
                        Toast.makeText(this, "Error: " + err, Toast.LENGTH_SHORT).show();
                    });
                }
            } catch (Exception e) {
                runOnUiThread(() -> {
                    pbLoading.setVisibility(View.GONE);
                    Toast.makeText(this, "Gagal terhubung: " + e.getMessage(), Toast.LENGTH_SHORT).show();
                });
            }
        }).start();
    }
}
