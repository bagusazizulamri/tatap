package id.tatap.app;

import android.app.Activity;
import android.app.Dialog;
import android.content.Context;
import android.graphics.Color;
import android.graphics.drawable.ColorDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextWatcher;
import android.util.Log;
import android.view.KeyEvent;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
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

    // Command Banner & Active Filter Bar Widgets
    private View layoutCommandBanner;
    private TextView tvCommandOutput;
    private Button btnCloseCommandBanner;
    private View layoutActiveFilter;
    private TextView tvActiveFilterLabel;
    private Button btnClearFilter;

    private final Handler bannerHandler = new Handler(Looper.getMainLooper());
    private final Runnable hideBannerRunnable = () -> {
        if (layoutCommandBanner != null) layoutCommandBanner.setVisibility(View.GONE);
    };

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

        // Command HUD & Filter Bar
        layoutCommandBanner = findViewById(R.id.layout_command_banner);
        tvCommandOutput = findViewById(R.id.tv_command_output);
        btnCloseCommandBanner = findViewById(R.id.btn_close_command_banner);
        layoutActiveFilter = findViewById(R.id.layout_active_filter);
        tvActiveFilterLabel = findViewById(R.id.tv_active_filter_label);
        btnClearFilter = findViewById(R.id.btn_clear_filter);

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
                        updateActiveFilterBar();
                        showCommandOutput("> tatap$ cari \"" + raw + "\"", false);
                        fetchData();
                    }
                }
                return true;
            }
            return false;
        });

        btnTabMusim.setOnClickListener(v -> {
            resetFiltersToTab("musim");
        });

        btnTabAiring.setOnClickListener(v -> {
            resetFiltersToTab("airing");
        });

        btnTabKatalog.setOnClickListener(v -> {
            resetFiltersToTab("katalog");
        });

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

        if (btnCloseCommandBanner != null) {
            btnCloseCommandBanner.setOnClickListener(v -> {
                if (layoutCommandBanner != null) layoutCommandBanner.setVisibility(View.GONE);
            });
        }

        if (btnClearFilter != null) {
            btnClearFilter.setOnClickListener(v -> resetFiltersToTab("musim"));
        }
    }

    private void showCommandOutput(String message, boolean isError) {
        if (layoutCommandBanner == null || tvCommandOutput == null) return;
        tvCommandOutput.setText(message);
        tvCommandOutput.setTextColor(isError ? 0xFFEF4444 : 0xFF00DBEB);
        layoutCommandBanner.setVisibility(View.VISIBLE);

        bannerHandler.removeCallbacks(hideBannerRunnable);
        bannerHandler.postDelayed(hideBannerRunnable, 8000);
    }

    private void updateActiveFilterBar() {
        if (layoutActiveFilter == null || tvActiveFilterLabel == null) return;

        if ("genre".equals(currentView)) {
            layoutActiveFilter.setVisibility(View.VISIBLE);
            tvActiveFilterLabel.setText("🏷 GENRE: " + currentGenre.toUpperCase().replace("-", " "));
        } else if ("season_filter".equals(currentView)) {
            layoutActiveFilter.setVisibility(View.VISIBLE);
            tvActiveFilterLabel.setText("❄ MUSIM: " + currentSeasonName.toUpperCase() + " " + currentSeasonYear);
        } else if ("cari".equals(currentView)) {
            layoutActiveFilter.setVisibility(View.VISIBLE);
            tvActiveFilterLabel.setText("🔍 CARI: \"" + currentSearchQuery + "\"");
        } else {
            layoutActiveFilter.setVisibility(View.GONE);
        }
    }

    private void resetFiltersToTab(String targetTab) {
        currentGenre = "";
        currentSeasonName = "";
        currentSeasonYear = 0;
        currentSearchQuery = "";
        etSearch.setText("");
        switchView(targetTab);
        updateActiveFilterBar();
        showCommandOutput("> tatap$ Tampilan diatur ke: " + targetTab.toUpperCase(), false);
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
                showCommandOutput("> tatap$ :help [Membuka Terminal Bantuan]", false);
                showCommandHelpDialog();
                break;

            case "musim":
                resetFiltersToTab("musim");
                break;

            case "season":
                if (!args.isEmpty()) {
                    handleSeasonFilterCommand(parts);
                } else {
                    showCommandOutput("> tatap$ Gunakan format: :season <winter|spring|summer|fall> <tahun>", true);
                    Toast.makeText(this, "Format: :season <winter|spring|summer|fall> <tahun> (Contoh: :season fall 2024)", Toast.LENGTH_LONG).show();
                }
                break;

            case "airing":
            case "terbaru":
                resetFiltersToTab("airing");
                break;

            case "katalog":
            case "catalog":
                resetFiltersToTab("katalog");
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
                    updateActiveFilterBar();
                    showCommandOutput("> tatap$ :cari \"" + args + "\" [Mencari...]", false);
                    fetchData();
                } else {
                    showCommandOutput("> tatap$ :cari [Gagal: Butuh kata kunci judul]", true);
                    Toast.makeText(this, "Gunakan: :cari <judul>", Toast.LENGTH_SHORT).show();
                }
                break;

            case "page":
            case "hal":
                try {
                    int p = Integer.parseInt(args);
                    if (p >= 1) {
                        currentPage = p;
                        showCommandOutput("> tatap$ :page " + p + " [Lompat ke Halaman " + p + "]", false);
                        fetchData();
                    }
                } catch (Exception e) {
                    showCommandOutput("> tatap$ :page [Gagal: Masukkan nomor halaman yang valid]", true);
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
                resetFiltersToTab("musim");
                break;

            default:
                showCommandOutput("> tatap$ Perintah tidak dikenal: :" + cmd + " (Ketik :help)", true);
                break;
        }
    }

    private void handleSeasonFilterCommand(String[] parts) {
        // Format: :season <winter|spring|summer|fall> [tahun]
        if (parts.length >= 2) {
            String sName = parts[1].toLowerCase();
            if (!sName.matches("^(winter|spring|summer|fall)$")) {
                showCommandOutput("> tatap$ Musim harus: winter, spring, summer, fall", true);
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
            updateActiveFilterBar();
            showCommandOutput("> tatap$ :season " + sName + " " + sYear + " [Filter Diterapkan]", false);
            fetchData();
        } else {
            showCommandOutput("> tatap$ Format: :season <winter|spring|summer|fall> <tahun>", true);
        }
    }

    private void setGenreFilter(String genreSlugOrTitle) {
        currentView = "genre";
        currentGenre = genreSlugOrTitle.toLowerCase().trim().replace(" ", "-");
        currentPage = 1;
        updateTabButtons();
        updateActiveFilterBar();
        showCommandOutput("> tatap$ :genre " + currentGenre + " [Filter Genre Aktif]", false);
        fetchData();
    }

    private void showGenreSelectorDialog() {
        Dialog dialog = new Dialog(this);
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE);
        dialog.setContentView(R.layout.dialog_genre_selector);
        if (dialog.getWindow() != null) {
            dialog.getWindow().setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
            dialog.getWindow().setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        }

        EditText etFilter = dialog.findViewById(R.id.et_filter_genre);
        ProgressBar pbGenre = dialog.findViewById(R.id.pb_genre_loading);
        RecyclerView rvGenres = dialog.findViewById(R.id.rv_genres);
        Button btnClose = dialog.findViewById(R.id.btn_close_genre_dialog);
        Button btnDismiss = dialog.findViewById(R.id.btn_dismiss_genre);
        Button btnReset = dialog.findViewById(R.id.btn_reset_genre_filter);

        rvGenres.setLayoutManager(new GridLayoutManager(this, 2));
        GenreChipAdapter genreAdapter = new GenreChipAdapter((slug, title) -> {
            dialog.dismiss();
            setGenreFilter(slug);
        });
        rvGenres.setAdapter(genreAdapter);

        btnClose.setOnClickListener(v -> dialog.dismiss());
        btnDismiss.setOnClickListener(v -> dialog.dismiss());
        btnReset.setOnClickListener(v -> {
            dialog.dismiss();
            resetFiltersToTab("musim");
        });

        etFilter.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {}
            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
                genreAdapter.filter(s.toString());
            }
            @Override
            public void afterTextChanged(Editable s) {}
        });

        dialog.show();

        // Fetch genres from backend
        new Thread(() -> {
            List<GenreItem> list = new ArrayList<>();
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
                    for (int i = 0; i < arr.length(); i++) {
                        JSONObject g = arr.getJSONObject(i);
                        list.add(new GenreItem(g.optString("title", ""), g.optString("slug", "")));
                    }
                }
            } catch (Exception ignored) {}

            if (list.isEmpty()) {
                // Fallback genres
                String[] fallback = new String[]{"Action", "Adventure", "Comedy", "Drama", "Fantasy", "Horror", "Mystery", "Romance", "Sci-Fi", "Slice of Life", "Sports", "Supernatural", "Isekai", "Psychological", "Thriller", "Magic"};
                for (String f : fallback) {
                    list.add(new GenreItem(f, f.toLowerCase().replace(" ", "-")));
                }
            }

            runOnUiThread(() -> {
                pbGenre.setVisibility(View.GONE);
                genreAdapter.setData(list);
            });
        }).start();
    }

    private void showCommandHelpDialog() {
        Dialog dialog = new Dialog(this);
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE);
        dialog.setContentView(R.layout.dialog_command_help);
        if (dialog.getWindow() != null) {
            dialog.getWindow().setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
            dialog.getWindow().setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        }

        Button btnClose = dialog.findViewById(R.id.btn_close_help_dialog);
        btnClose.setOnClickListener(v -> dialog.dismiss());

        dialog.findViewById(R.id.cmd_item_musim).setOnClickListener(v -> {
            dialog.dismiss();
            resetFiltersToTab("musim");
        });

        dialog.findViewById(R.id.cmd_item_season).setOnClickListener(v -> {
            dialog.dismiss();
            etSearch.setText(":season fall 2024");
            etSearch.setSelection(etSearch.getText().length());
            etSearch.requestFocus();
            showCommandOutput("> tatap$ Silakan tentukan musim & tahun lalu tekan Enter", false);
        });

        dialog.findViewById(R.id.cmd_item_genre).setOnClickListener(v -> {
            dialog.dismiss();
            showGenreSelectorDialog();
        });

        dialog.findViewById(R.id.cmd_item_airing).setOnClickListener(v -> {
            dialog.dismiss();
            resetFiltersToTab("airing");
        });

        dialog.findViewById(R.id.cmd_item_katalog).setOnClickListener(v -> {
            dialog.dismiss();
            resetFiltersToTab("katalog");
        });

        dialog.findViewById(R.id.cmd_item_source).setOnClickListener(v -> {
            dialog.dismiss();
            switchDefaultSource("otakudesu");
        });

        dialog.findViewById(R.id.cmd_item_ping).setOnClickListener(v -> {
            dialog.dismiss();
            checkBackendStatus();
        });

        dialog.findViewById(R.id.cmd_item_clear).setOnClickListener(v -> {
            dialog.dismiss();
            resetFiltersToTab("musim");
        });

        dialog.show();
    }

    private void switchDefaultSource(String target) {
        String s = target.toLowerCase().trim();
        String newSrc = s.contains("otaku") ? "otakudesu" : "hianime";

        showCommandOutput("> tatap$ :source " + newSrc + " [Mengalihkan sumber...]", false);

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
                    String label = newSrc.equals("otakudesu") ? "Otakudesu (Sub Indo)" : "HiAnime (Multi-Sub)";
                    showCommandOutput("> tatap$ [OK] Sumber default berhasil diubah ke " + label, false);
                    fetchData();
                });
            } catch (Exception e) {
                runOnUiThread(() -> showCommandOutput("> tatap$ [ERROR] Gagal ubah sumber: " + e.getMessage(), true));
            }
        }).start();
    }

    private void checkBackendStatus() {
        showCommandOutput("> tatap$ :ping [Memeriksa 127.0.0.1:8767...]", false);
        new Thread(() -> {
            try {
                long start = System.currentTimeMillis();
                HttpURLConnection conn = (HttpURLConnection) new URL("http://127.0.0.1:8767/api/ping").openConnection();
                conn.setConnectTimeout(2000);
                int code = conn.getResponseCode();
                long elapsed = System.currentTimeMillis() - start;
                conn.disconnect();
                runOnUiThread(() -> {
                    if (code == 200) {
                        showCommandOutput("> tatap$ [PONG] Backend ONLINE (127.0.0.1:8767 OK, " + elapsed + "ms)", false);
                    } else {
                        showCommandOutput("> tatap$ [WARN] Backend responded HTTP " + code, true);
                    }
                });
            } catch (Exception e) {
                runOnUiThread(() -> showCommandOutput("> tatap$ [OFFLINE] Backend tidak terhubung: " + e.getMessage(), true));
            }
        }).start();
    }

    private void switchView(String targetView) {
        currentView = targetView;
        currentPage = 1;
        updateTabButtons();
        updateActiveFilterBar();
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
                    showCommandOutput("> tatap$ Gagal start backend: " + t.getMessage(), true);
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
                    showCommandOutput("> tatap$ Server butuh inisialisasi lebih lama. Ketuk badge status untuk mencoba ulang.", true);
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
            title = "Genre: " + currentGenre.toUpperCase().replace("-", " ") + " (Hal " + currentPage + ")";
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
                        showCommandOutput("> tatap$ [ERROR] " + err, true);
                    });
                }
            } catch (Exception e) {
                runOnUiThread(() -> {
                    pbLoading.setVisibility(View.GONE);
                    showCommandOutput("> tatap$ [ERROR] Gagal terhubung: " + e.getMessage(), true);
                });
            }
        }).start();
    }

    // Model & Adapter for Genre Dialog
    static class GenreItem {
        final String title;
        final String slug;
        GenreItem(String title, String slug) {
            this.title = title;
            this.slug = slug;
        }
    }

    interface OnGenreClickListener {
        void onGenreClick(String slug, String title);
    }

    static class GenreChipAdapter extends RecyclerView.Adapter<GenreChipAdapter.ViewHolder> {
        private final List<GenreItem> allGenres = new ArrayList<>();
        private final List<GenreItem> filteredList = new ArrayList<>();
        private final OnGenreClickListener listener;

        GenreChipAdapter(OnGenreClickListener listener) {
            this.listener = listener;
        }

        void setData(List<GenreItem> data) {
            allGenres.clear();
            filteredList.clear();
            if (data != null) {
                allGenres.addAll(data);
                filteredList.addAll(data);
            }
            notifyDataSetChanged();
        }

        void filter(String query) {
            filteredList.clear();
            if (query == null || query.trim().isEmpty()) {
                filteredList.addAll(allGenres);
            } else {
                String q = query.toLowerCase().trim();
                for (GenreItem item : allGenres) {
                    if (item.title.toLowerCase().contains(q) || item.slug.toLowerCase().contains(q)) {
                        filteredList.add(item);
                    }
                }
            }
            notifyDataSetChanged();
        }

        @NonNull
        @Override
        public ViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
            View v = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_genre_chip, parent, false);
            return new ViewHolder(v);
        }

        @Override
        public void onBindViewHolder(@NonNull ViewHolder holder, int position) {
            GenreItem item = filteredList.get(position);
            holder.tvName.setText(item.title);
            holder.itemView.setOnClickListener(v -> {
                if (listener != null) listener.onGenreClick(item.slug, item.title);
            });
        }

        @Override
        public int getItemCount() {
            return filteredList.size();
        }

        static class ViewHolder extends RecyclerView.ViewHolder {
            TextView tvName;
            ViewHolder(@NonNull View itemView) {
                super(itemView);
                tvName = itemView.findViewById(R.id.tv_genre_name);
            }
        }
    }
}
