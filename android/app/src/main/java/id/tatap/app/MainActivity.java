package id.tatap.app;

import android.app.Activity;
import android.app.AlertDialog;
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
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

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
    private TextView btnClearSearch;
    private ProgressBar pbLoading;
    private TextView tvSectionTitle, tvItemCount, tvStatusBadge, tvPageIndicator;
    private RecyclerView rvGrid;
    private AnimeAdapter adapter;
    private SwipeRefreshLayout swipeRefreshLayout;

    // Header Quick Actions
    private TextView btnHeaderAi, btnHeaderGenre, btnHeaderHelp, btnHeaderHistory;

    // Segmented Tabs & Pagination
    private TextView btnTabMusim, btnTabAiring, btnTabKatalog;
    private TextView btnPrevPage, btnNextPage;
    private View layoutPagination;

    // Empty / Error State Layout
    private View layoutEmptyState;
    private TextView tvEmptyTitle, tvEmptyDesc, btnEmptyRetry;

    // Command Banner & Active Filter Bar Widgets
    private View layoutCommandBanner;
    private TextView tvCommandOutput;
    private Button btnCloseCommandBanner;
    private View layoutActiveFilter;
    private TextView tvActiveFilterLabel;
    private Button btnClearFilter;
    private TextView btnClearHistoryAll;

    private final Handler bannerHandler = new Handler(Looper.getMainLooper());
    private final Runnable hideBannerRunnable = () -> {
        if (layoutCommandBanner != null) layoutCommandBanner.setVisibility(View.GONE);
    };

    // State navigasi tampilan & paging
    private String currentView = "musim"; // "musim" | "airing" | "katalog" | "cari" | "genre" | "season_filter" | "riwayat"
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
        btnClearSearch = findViewById(R.id.btn_clear_search);
        pbLoading = findViewById(R.id.pb_loading);
        tvSectionTitle = findViewById(R.id.tv_section_title);
        tvItemCount = findViewById(R.id.tv_item_count);
        tvStatusBadge = findViewById(R.id.tv_status_badge);
        tvPageIndicator = findViewById(R.id.tv_page_indicator);
        rvGrid = findViewById(R.id.rv_anime_grid);
        swipeRefreshLayout = findViewById(R.id.swipe_refresh_layout);

        btnHeaderAi = findViewById(R.id.btn_header_ai);
        btnHeaderGenre = findViewById(R.id.btn_header_genre);
        btnHeaderHelp = findViewById(R.id.btn_header_help);
        btnHeaderHistory = findViewById(R.id.btn_header_history);

        btnTabMusim = findViewById(R.id.btn_tab_musim);
        btnTabAiring = findViewById(R.id.btn_tab_airing);
        btnTabKatalog = findViewById(R.id.btn_tab_katalog);
        btnPrevPage = findViewById(R.id.btn_prev_page);
        btnNextPage = findViewById(R.id.btn_next_page);
        layoutPagination = findViewById(R.id.layout_pagination);

        layoutEmptyState = findViewById(R.id.layout_empty_state);
        tvEmptyTitle = findViewById(R.id.tv_empty_title);
        tvEmptyDesc = findViewById(R.id.tv_empty_desc);
        btnEmptyRetry = findViewById(R.id.btn_empty_retry);

        // Command HUD & Filter Bar
        layoutCommandBanner = findViewById(R.id.layout_command_banner);
        tvCommandOutput = findViewById(R.id.tv_command_output);
        btnCloseCommandBanner = findViewById(R.id.btn_close_command_banner);
        layoutActiveFilter = findViewById(R.id.layout_active_filter);
        tvActiveFilterLabel = findViewById(R.id.tv_active_filter_label);
        btnClearFilter = findViewById(R.id.btn_clear_filter);
        btnClearHistoryAll = findViewById(R.id.btn_clear_history_all);

        int spanCount = getResources().getInteger(R.integer.anime_grid_columns);
        rvGrid.setLayoutManager(new GridLayoutManager(this, spanCount));
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

        if (btnHeaderAi != null) {
            btnHeaderAi.setOnClickListener(v -> showAiSettingsDialog());
        }

        if (btnHeaderGenre != null) {
            btnHeaderGenre.setOnClickListener(v -> showGenreSelectorDialog());
        }

        if (btnHeaderHelp != null) {
            btnHeaderHelp.setOnClickListener(v -> showCommandHelpDialog());
        }

        if (btnHeaderHistory != null) {
            btnHeaderHistory.setOnClickListener(v -> switchView("riwayat"));
        }

        if (btnClearHistoryAll != null) {
            btnClearHistoryAll.setOnClickListener(v -> confirmAndClearHistory());
        }

        if (btnClearSearch != null) {
            btnClearSearch.setOnClickListener(v -> {
                etSearch.setText("");
                if ("cari".equals(currentView)) {
                    resetFiltersToTab("musim");
                }
            });
        }

        etSearch.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {}

            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
                if (btnClearSearch != null) {
                    btnClearSearch.setVisibility(s != null && s.length() > 0 ? View.VISIBLE : View.GONE);
                }
            }

            @Override
            public void afterTextChanged(Editable s) {}
        });

        if (swipeRefreshLayout != null) {
            swipeRefreshLayout.setColorSchemeColors(0xFF00DBEB, 0xFF0E7490);
            swipeRefreshLayout.setProgressBackgroundColorSchemeColor(0xFF0E121C);
            swipeRefreshLayout.setOnRefreshListener(this::fetchData);
        }

        if (btnEmptyRetry != null) {
            btnEmptyRetry.setOnClickListener(v -> fetchData());
        }

        if (tvStatusBadge != null) {
            tvStatusBadge.setOnClickListener(v -> checkBackendStatus());
        }
    }

    private void showCommandOutput(String message, boolean isError) {
        if (layoutCommandBanner == null || tvCommandOutput == null) return;
        tvCommandOutput.setText(message);
        tvCommandOutput.setTextColor(isError ? 0xFFEF4444 : 0xFF38BDF8);
        layoutCommandBanner.setVisibility(View.VISIBLE);

        bannerHandler.removeCallbacks(hideBannerRunnable);
        bannerHandler.postDelayed(hideBannerRunnable, 8000);
    }

    private void updateActiveFilterBar() {
        if (layoutActiveFilter == null || tvActiveFilterLabel == null) return;

        if ("genre".equals(currentView)) {
            layoutActiveFilter.setVisibility(View.VISIBLE);
            tvActiveFilterLabel.setText("🏷 GENRE: " + currentGenre.toUpperCase().replace("-", " "));
            if (btnClearHistoryAll != null) btnClearHistoryAll.setVisibility(View.GONE);
        } else if ("season_filter".equals(currentView)) {
            layoutActiveFilter.setVisibility(View.VISIBLE);
            tvActiveFilterLabel.setText("❄ MUSIM: " + currentSeasonName.toUpperCase() + " " + currentSeasonYear);
            if (btnClearHistoryAll != null) btnClearHistoryAll.setVisibility(View.GONE);
        } else if ("cari".equals(currentView)) {
            layoutActiveFilter.setVisibility(View.VISIBLE);
            tvActiveFilterLabel.setText("🔍 CARI: \"" + currentSearchQuery + "\"");
            if (btnClearHistoryAll != null) btnClearHistoryAll.setVisibility(View.GONE);
        } else if ("riwayat".equals(currentView)) {
            layoutActiveFilter.setVisibility(View.VISIBLE);
            tvActiveFilterLabel.setText("🕒 RIWAYAT TONTONAN");
            if (btnClearHistoryAll != null) btnClearHistoryAll.setVisibility(View.VISIBLE);
        } else {
            layoutActiveFilter.setVisibility(View.GONE);
            if (btnClearHistoryAll != null) btnClearHistoryAll.setVisibility(View.GONE);
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

            case "ai":
            case "aitranslate":
                showAiSettingsDialog();
                break;

            case "apikey":
            case "ollama":
            case "groq":
            case "gemini":
            case "openai":
            case "model":
            case "apiurl":
                cmdTranslateSetting(cmd, args);
                break;

            case "riwayat":
            case "history":
            case "lanjutan":
                if (args.equalsIgnoreCase("clear") || args.equalsIgnoreCase("hapus") || args.equalsIgnoreCase("reset")) {
                    clearWatchHistory();
                } else {
                    switchView("riwayat");
                    showCommandOutput("> tatap$ :riwayat [Menampilkan Riwayat Tontonan]", false);
                }
                break;

            case "logs":
            case "translog":
                showTranslateLogsDialog();
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

        int genreSpan = getResources().getInteger(R.integer.genre_dialog_columns);
        rvGenres.setLayoutManager(new GridLayoutManager(this, genreSpan));
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
                        String slug = g.optString("slug", "");
                        String title = g.optString("title", "");
                        if ("hentai".equalsIgnoreCase(slug) || title.toLowerCase().contains("hentai")) {
                            continue;
                        }
                        list.add(new GenreItem(title, slug));
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

        dialog.findViewById(R.id.cmd_item_ai).setOnClickListener(v -> {
            dialog.dismiss();
            showAiSettingsDialog();
        });

        dialog.findViewById(R.id.cmd_item_apikey).setOnClickListener(v -> {
            dialog.dismiss();
            cmdTranslateSetting("apikey", "");
        });

        dialog.findViewById(R.id.cmd_item_gemini).setOnClickListener(v -> {
            dialog.dismiss();
            etSearch.setText(":gemini ");
            etSearch.setSelection(8);
            etSearch.requestFocus();
            showCommandOutput("> tatap$ Masukkan API key Google AI Studio (AQ...) Anda", false);
        });

        dialog.findViewById(R.id.cmd_item_groq).setOnClickListener(v -> {
            dialog.dismiss();
            etSearch.setText(":groq ");
            etSearch.setSelection(6);
            etSearch.requestFocus();
            showCommandOutput("> tatap$ Masukkan API key Groq Cloud (gsk_...) Anda", false);
        });

        dialog.findViewById(R.id.cmd_item_ollama).setOnClickListener(v -> {
            dialog.dismiss();
            etSearch.setText(":ollama ");
            etSearch.setSelection(8);
            etSearch.requestFocus();
            showCommandOutput("> tatap$ Masukkan API key Ollama Cloud Anda", false);
        });

        dialog.findViewById(R.id.cmd_item_model).setOnClickListener(v -> {
            dialog.dismiss();
            cmdTranslateSetting("model", "");
        });

        dialog.findViewById(R.id.cmd_item_logs).setOnClickListener(v -> {
            dialog.dismiss();
            showTranslateLogsDialog();
        });

        View itemRiwayat = dialog.findViewById(R.id.cmd_item_riwayat);
        if (itemRiwayat != null) {
            itemRiwayat.setOnClickListener(v -> {
                dialog.dismiss();
                switchView("riwayat");
            });
        }

        dialog.findViewById(R.id.cmd_item_clear).setOnClickListener(v -> {
            dialog.dismiss();
            resetFiltersToTab("musim");
        });

        dialog.show();
    }

    private String maskKey(String key) {
        if (key == null || key.isEmpty()) return "(kosong)";
        if (key.length() <= 10) return "****";
        int prefixLen = key.startsWith("AQ.") ? 6 : (key.length() > 14 ? 8 : 4);
        return key.substring(0, prefixLen) + "..." + key.substring(key.length() - 4);
    }

    private void cmdTranslateSetting(String cmd, String rawArgs) {
        String args = rawArgs != null ? rawArgs.trim() : "";
        if (cmd.equals("apikey") || cmd.equals("ollama") || cmd.equals("groq") || cmd.equals("gemini") || cmd.equals("openai")) {
            args = args.replaceAll("^[\"']|[\"']$", "").trim();
        }

        if (args.isEmpty()) {
            showCommandOutput("> tatap$ Membaca status AI Translate...", false);
            new Thread(() -> {
                try {
                    HttpURLConnection conn = (HttpURLConnection) new URL("http://127.0.0.1:8767/api/settings").openConnection();
                    conn.setConnectTimeout(3000);
                    BufferedReader r = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                    StringBuilder sb = new StringBuilder();
                    String line;
                    while ((line = r.readLine()) != null) sb.append(line);
                    r.close();

                    JSONObject res = new JSONObject(sb.toString());
                    JSONObject d = res.optJSONObject("data");
                    if (d == null) d = res;
                    String key = d.optString("translate_apikey", "");
                    String model = d.optString("translate_model", "gemini-3.1-flash-lite");
                    String url = d.optString("translate_apiurl", "https://generativelanguage.googleapis.com/v1beta/openai");

                    runOnUiThread(() -> {
                        String out = "> tatap$ [AI STATUS] apikey: " + maskKey(key) + " | model: " + model;
                        showCommandOutput(out, false);
                        showAiSettingsDialog();
                    });
                } catch (Exception e) {
                    runOnUiThread(() -> showCommandOutput("> tatap$ [ERROR] Gagal membaca setelan: " + e.getMessage(), true));
                }
            }).start();
            return;
        }

        if (args.equalsIgnoreCase("clear") || args.equalsIgnoreCase("reset")) {
            JSONObject body = new JSONObject();
            try {
                if (cmd.equals("model")) body.put("translate_model", "gemini-3.1-flash-lite");
                else if (cmd.equals("apiurl")) body.put("translate_apiurl", "https://generativelanguage.googleapis.com/v1beta/openai");
                else body.put("translate_apikey", "");
            } catch (Exception ignored) {}

            saveAiSettingsAndReport(body, cmd + " direset ke default");
            return;
        }

        JSONObject body = new JSONObject();
        String extra = "";
        try {
            if (cmd.equals("model")) {
                body.put("translate_model", args);
                extra = " [model disetel ke " + args + "]";
            } else if (cmd.equals("apiurl")) {
                body.put("translate_apiurl", args);
                extra = " [apiurl disetel ke " + args + "]";
            } else {
                body.put("translate_apikey", args);
                boolean isOllama = cmd.equals("ollama") || args.startsWith("ollama_") || args.startsWith("ol_") || args.matches("^[a-f0-9]{32}\\.[A-Za-z0-9_-]+$");
                if (isOllama) {
                    body.put("translate_apiurl", "https://ollama.com/v1");
                    body.put("translate_model", "gpt-oss:20b");
                    extra = " [Auto: Ollama Cloud (gpt-oss:20b)]";
                } else if (cmd.equals("gemini") || args.startsWith("AQ.") || args.startsWith("AIza") || args.startsWith("AQ")) {
                    body.put("translate_apiurl", "https://generativelanguage.googleapis.com/v1beta/openai");
                    body.put("translate_model", "gemini-3.1-flash-lite");
                    extra = " [Auto: Google AI Studio (gemini-3.1-flash-lite)]";
                } else if (cmd.equals("groq") || args.startsWith("gsk_")) {
                    body.put("translate_apiurl", "https://api.groq.com/openai/v1");
                    body.put("translate_model", "llama-3.3-70b-versatile");
                    extra = " [Auto: Groq Cloud (llama-3.3-70b-versatile)]";
                } else if (args.startsWith("sk-or-")) {
                    body.put("translate_apiurl", "https://openrouter.ai/api/v1");
                    body.put("translate_model", "google/gemini-2.0-flash-exp:free");
                    extra = " [Auto: OpenRouter (gemini-2.0-flash-exp)]";
                } else if (cmd.equals("openai") || args.startsWith("sk-") || args.startsWith("sk_")) {
                    body.put("translate_apiurl", "https://api.openai.com/v1");
                    body.put("translate_model", "gpt-4o-mini");
                    extra = " [Auto: OpenAI (gpt-4o-mini)]";
                } else {
                    extra = " [Provider Custom]";
                }
            }
        } catch (Exception ignored) {}

        String masked = maskKey(args);
        saveAiSettingsAndReport(body, cmd + " disimpan (" + masked + ")" + extra);
    }

    private void saveAiSettingsAndReport(JSONObject payload, String successMsg) {
        new Thread(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL("http://127.0.0.1:8767/api/settings").openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setDoOutput(true);
                conn.getOutputStream().write(payload.toString().getBytes("UTF-8"));
                conn.getInputStream().close();
                runOnUiThread(() -> {
                    showCommandOutput("> tatap$ [OK] " + successMsg, false);
                    Toast.makeText(this, successMsg, Toast.LENGTH_SHORT).show();
                });
            } catch (Exception e) {
                runOnUiThread(() -> showCommandOutput("> tatap$ [ERROR] Gagal menyimpan: " + e.getMessage(), true));
            }
        }).start();
    }

    private void showTranslateLogsDialog() {
        Dialog dialog = new Dialog(this);
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE);
        dialog.setContentView(R.layout.dialog_translate_logs);
        if (dialog.getWindow() != null) {
            dialog.getWindow().setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
            dialog.getWindow().setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        }

        TextView tvLogs = dialog.findViewById(R.id.tv_translate_logs_content);
        Button btnClose = dialog.findViewById(R.id.btn_close_logs_dialog);
        Button btnDismiss = dialog.findViewById(R.id.btn_dismiss_logs);
        Button btnRefresh = dialog.findViewById(R.id.btn_refresh_logs);

        btnClose.setOnClickListener(v -> dialog.dismiss());
        btnDismiss.setOnClickListener(v -> dialog.dismiss());

        Runnable loadLogs = () -> {
            tvLogs.setText("Mengambil log terbaru dari server...");
            new Thread(() -> {
                try {
                    HttpURLConnection conn = (HttpURLConnection) new URL("http://127.0.0.1:8767/api/translate/logs").openConnection();
                    conn.setConnectTimeout(3000);
                    BufferedReader r = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                    StringBuilder sb = new StringBuilder();
                    String line;
                    while ((line = r.readLine()) != null) sb.append(line);
                    r.close();

                    JSONObject res = new JSONObject(sb.toString());
                    JSONArray arr = res.getJSONObject("data").getJSONArray("logs");
                    StringBuilder logText = new StringBuilder();
                    for (int i = 0; i < arr.length(); i++) {
                        logText.append("• ").append(arr.getString(i)).append("\n\n");
                    }
                    if (arr.length() == 0) {
                        logText.append("(Belum ada aktivitas translasi subtitle yang tercatat)");
                    }
                    runOnUiThread(() -> tvLogs.setText(logText.toString().trim()));
                } catch (Exception e) {
                    runOnUiThread(() -> tvLogs.setText("Gagal membaca log: " + e.getMessage()));
                }
            }).start();
        };

        btnRefresh.setOnClickListener(v -> loadLogs.run());
        dialog.show();
        loadLogs.run();
    }

    private void showAiSettingsDialog() {
        Dialog dialog = new Dialog(this);
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE);
        dialog.setContentView(R.layout.dialog_ai_settings);
        if (dialog.getWindow() != null) {
            dialog.getWindow().setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
            dialog.getWindow().setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        }

        TextView tvKey = dialog.findViewById(R.id.tv_ai_status_key);
        TextView tvModel = dialog.findViewById(R.id.tv_ai_status_model);
        TextView tvUrl = dialog.findViewById(R.id.tv_ai_status_url);
        EditText etKey = dialog.findViewById(R.id.et_ai_apikey);
        EditText etModel = dialog.findViewById(R.id.et_ai_model);
        EditText etUrl = dialog.findViewById(R.id.et_ai_apiurl);

        Button btnClose = dialog.findViewById(R.id.btn_close_ai_dialog);
        Button btnSave = dialog.findViewById(R.id.btn_ai_save);
        Button btnReset = dialog.findViewById(R.id.btn_ai_reset_key);
        Button btnLogs = dialog.findViewById(R.id.btn_ai_view_logs);

        Button btnPresetGemini = dialog.findViewById(R.id.btn_preset_gemini);
        Button btnPresetGroq = dialog.findViewById(R.id.btn_preset_groq);
        Button btnPresetOllama = dialog.findViewById(R.id.btn_preset_ollama);
        Button btnPresetOpenAI = dialog.findViewById(R.id.btn_preset_openai);

        btnClose.setOnClickListener(v -> dialog.dismiss());

        etKey.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {}
            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
                String k = s.toString().trim();
                if (k.startsWith("gsk_")) {
                    etModel.setText("llama-3.3-70b-versatile");
                    etUrl.setText("https://api.groq.com/openai/v1");
                    tvKey.setText("API Key : " + maskKey(k) + " (Groq Cloud)");
                } else if (k.startsWith("AQ.") || k.startsWith("AIza") || k.startsWith("AQ")) {
                    etModel.setText("gemini-3.1-flash-lite");
                    etUrl.setText("https://generativelanguage.googleapis.com/v1beta/openai");
                    tvKey.setText("API Key : " + maskKey(k) + " (Google AI Studio)");
                } else if (k.startsWith("sk-or-")) {
                    etModel.setText("google/gemini-2.0-flash-exp:free");
                    etUrl.setText("https://openrouter.ai/api/v1");
                    tvKey.setText("API Key : " + maskKey(k) + " (OpenRouter)");
                } else if (k.startsWith("ollama_") || k.startsWith("ol_") || (k.length() > 35 && k.contains("."))) {
                    etModel.setText("gpt-oss:20b");
                    etUrl.setText("https://ollama.com/v1");
                    tvKey.setText("API Key : " + maskKey(k) + " (Ollama Cloud)");
                } else if (k.startsWith("sk-") || k.startsWith("sk_")) {
                    etModel.setText("gpt-4o-mini");
                    etUrl.setText("https://api.openai.com/v1");
                    tvKey.setText("API Key : " + maskKey(k) + " (OpenAI)");
                }
            }
            @Override
            public void afterTextChanged(Editable s) {}
        });

        btnLogs.setOnClickListener(v -> {
            dialog.dismiss();
            showTranslateLogsDialog();
        });

        btnPresetGemini.setOnClickListener(v -> {
            etModel.setText("gemini-3.1-flash-lite");
            etUrl.setText("https://generativelanguage.googleapis.com/v1beta/openai");
            etKey.setHint("Tempel kunci Google AI (AQ...)");
            Toast.makeText(this, "Preset Google Gemini dipilih", Toast.LENGTH_SHORT).show();
        });

        btnPresetGroq.setOnClickListener(v -> {
            etModel.setText("llama-3.3-70b-versatile");
            etUrl.setText("https://api.groq.com/openai/v1");
            etKey.setHint("Tempel kunci Groq Cloud (gsk_...)");
            Toast.makeText(this, "Preset Groq Cloud dipilih", Toast.LENGTH_SHORT).show();
        });

        btnPresetOllama.setOnClickListener(v -> {
            etModel.setText("gpt-oss:20b");
            etUrl.setText("https://ollama.com/v1");
            etKey.setHint("Tempel kunci Ollama Cloud");
            Toast.makeText(this, "Preset Ollama Cloud dipilih", Toast.LENGTH_SHORT).show();
        });

        btnPresetOpenAI.setOnClickListener(v -> {
            etModel.setText("gpt-4o-mini");
            etUrl.setText("https://api.openai.com/v1");
            etKey.setHint("Tempel kunci OpenAI (sk-...)");
            Toast.makeText(this, "Preset OpenAI dipilih", Toast.LENGTH_SHORT).show();
        });

        btnReset.setOnClickListener(v -> {
            dialog.dismiss();
            cmdTranslateSetting("apikey", "reset");
        });

        btnSave.setOnClickListener(v -> {
            String newKey = etKey.getText().toString().trim();
            String newModel = etModel.getText().toString().trim();
            String newUrl = etUrl.getText().toString().trim();

            JSONObject payload = new JSONObject();
            try {
                if (!newKey.isEmpty()) payload.put("translate_apikey", newKey);
                if (!newModel.isEmpty()) payload.put("translate_model", newModel);
                if (!newUrl.isEmpty()) payload.put("translate_apiurl", newUrl);
            } catch (Exception ignored) {}

            dialog.dismiss();
            saveAiSettingsAndReport(payload, "Pengaturan AI Translate disimpan");
        });

        // Fetch current settings
        new Thread(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL("http://127.0.0.1:8767/api/settings").openConnection();
                conn.setConnectTimeout(3000);
                BufferedReader r = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = r.readLine()) != null) sb.append(line);
                r.close();

                JSONObject res = new JSONObject(sb.toString());
                JSONObject d = res.optJSONObject("data");
                if (d == null) d = res;
                String k = d.optString("translate_apikey", "");
                String m = d.optString("translate_model", "gemini-3.1-flash-lite");
                String u = d.optString("translate_apiurl", "https://generativelanguage.googleapis.com/v1beta/openai");

                runOnUiThread(() -> {
                    tvKey.setText("API Key : " + maskKey(k));
                    tvModel.setText("Model   : " + m);
                    tvUrl.setText("API URL : " + u);
                    etModel.setText(m);
                    etUrl.setText(u);
                });
            } catch (Exception ignored) {}
        }).start();

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
                        tvStatusBadge.setText("● ONLINE");
                        tvStatusBadge.setTextColor(0xFF10B981);
                        tvStatusBadge.setBackgroundResource(R.drawable.bg_status_pill);
                        showCommandOutput("> tatap$ [PONG] Backend ONLINE (127.0.0.1:8767 OK, " + elapsed + "ms)", false);
                    } else {
                        tvStatusBadge.setText("● OFFLINE");
                        tvStatusBadge.setTextColor(0xFFEF4444);
                        tvStatusBadge.setBackgroundResource(R.drawable.bg_status_pill_err);
                        showCommandOutput("> tatap$ [WARN] Backend responded HTTP " + code, true);
                    }
                });
            } catch (Exception e) {
                runOnUiThread(() -> {
                    tvStatusBadge.setText("● OFFLINE");
                    tvStatusBadge.setTextColor(0xFFEF4444);
                    tvStatusBadge.setBackgroundResource(R.drawable.bg_status_pill_err);
                    showCommandOutput("> tatap$ [OFFLINE] Backend tidak terhubung: " + e.getMessage(), true);
                });
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
        boolean isMusim = "musim".equals(currentView);
        boolean isAiring = "airing".equals(currentView);
        boolean isKatalog = "katalog".equals(currentView);
        boolean isRiwayat = "riwayat".equals(currentView);

        btnTabMusim.setBackgroundResource(isMusim ? R.drawable.bg_tab_active : R.drawable.bg_tab_inactive);
        btnTabMusim.setTextColor(isMusim ? 0xFFFFFFFF : 0xFF8892B0);

        btnTabAiring.setBackgroundResource(isAiring ? R.drawable.bg_tab_active : R.drawable.bg_tab_inactive);
        btnTabAiring.setTextColor(isAiring ? 0xFFFFFFFF : 0xFF8892B0);

        btnTabKatalog.setBackgroundResource(isKatalog ? R.drawable.bg_tab_active : R.drawable.bg_tab_inactive);
        btnTabKatalog.setTextColor(isKatalog ? 0xFFFFFFFF : 0xFF8892B0);

        if (btnHeaderHistory != null) {
            btnHeaderHistory.setTextColor(isRiwayat ? 0xFF38BDF8 : 0xFF94A3B8);
        }
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
                    tvStatusBadge.setText("● ONLINE");
                    tvStatusBadge.setTextColor(0xFF10B981);
                    tvStatusBadge.setBackgroundResource(R.drawable.bg_status_pill);
                    fetchData();
                });
            } else if (attempt < 45) { // Coba sampai ~22 detik
                runOnUiThread(() -> {
                    if (attempt % 5 == 0 && attempt > 0) {
                        tvStatusBadge.setText("● INIT " + (attempt * 2) + "%");
                        tvStatusBadge.setTextColor(0xFFF59E0B);
                        tvStatusBadge.setBackgroundResource(R.drawable.bg_status_pill_warn);
                    }
                });
                try { Thread.sleep(500); } catch (Exception ignored) {}
                waitForServerAndLoadCatalog(attempt + 1);
            } else {
                runOnUiThread(() -> {
                    tvStatusBadge.setText("● OFFLINE");
                    tvStatusBadge.setTextColor(0xFFEF4444);
                    tvStatusBadge.setBackgroundResource(R.drawable.bg_status_pill_err);
                    showCommandOutput("> tatap$ Server butuh inisialisasi lebih lama. Ketuk badge status untuk mencoba ulang.", true);
                    tvStatusBadge.setOnClickListener(v -> {
                        tvStatusBadge.setText("● RETRYING...");
                        tvStatusBadge.setTextColor(0xFFF59E0B);
                        tvStatusBadge.setBackgroundResource(R.drawable.bg_status_pill_warn);
                        startEmbeddedBackend();
                        waitForServerAndLoadCatalog(0);
                    });
                    fetchData();
                });
            }
        }).start();
    }

    private void fetchData() {
        if (pbLoading != null) pbLoading.setVisibility(View.VISIBLE);
        tvPageIndicator.setText("Hal " + currentPage);
        btnPrevPage.setEnabled(currentPage > 1);
        btnPrevPage.setAlpha(currentPage > 1 ? 1.0f : 0.4f);

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
        } else if ("riwayat".equals(currentView)) {
            title = "Riwayat Tontonan";
            endpoint = "/api/history";
        } else {
            title = "Hasil Pencarian: " + currentSearchQuery;
            endpoint = "/api/search?q=" + URLEncoder.encode(currentSearchQuery) + "&limit=24";
        }

        tvSectionTitle.setText(title);
        if (layoutPagination != null) {
            layoutPagination.setVisibility("riwayat".equals(currentView) ? View.GONE : View.VISIBLE);
        }

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
                    JSONArray arr = res.optJSONArray("data");
                    if (arr == null) {
                        JSONObject data = res.optJSONObject("data");
                        if (data != null) {
                            arr = data.optJSONArray("results");
                            if (arr == null) arr = data.optJSONArray("items");
                        }
                    }
                    if (arr == null) arr = new JSONArray();

                    List<JSONObject> list = new ArrayList<>();
                    for (int i = 0; i < arr.length(); i++) {
                        list.add(arr.getJSONObject(i));
                    }

                    final int count = list.size();
                    runOnUiThread(() -> {
                        if (pbLoading != null) pbLoading.setVisibility(View.GONE);
                        if (swipeRefreshLayout != null) swipeRefreshLayout.setRefreshing(false);
                        tvItemCount.setText(count + " judul");
                        adapter.setData(list);
                        btnNextPage.setEnabled(count >= 10);
                        btnNextPage.setAlpha(count >= 10 ? 1.0f : 0.4f);

                        if (count == 0) {
                            if (layoutEmptyState != null) {
                                layoutEmptyState.setVisibility(View.VISIBLE);
                                if ("riwayat".equals(currentView)) {
                                    tvEmptyTitle.setText("Belum Ada Riwayat Tontonan");
                                    tvEmptyDesc.setText("Anime yang Anda tonton akan otomatis tercatat di sini.");
                                } else {
                                    tvEmptyTitle.setText("Tidak Ada Anime Ditemukan");
                                    tvEmptyDesc.setText("Tidak ada judul anime yang cocok dengan filter atau pencarian ini.");
                                }
                            }
                            if (rvGrid != null) rvGrid.setVisibility(View.GONE);
                        } else {
                            if (layoutEmptyState != null) layoutEmptyState.setVisibility(View.GONE);
                            if (rvGrid != null) {
                                rvGrid.setVisibility(View.VISIBLE);
                                rvGrid.scrollToPosition(0);
                            }
                        }
                    });
                } else {
                    final String err = res.optString("error", "gagal memuat data");
                    runOnUiThread(() -> {
                        if (pbLoading != null) pbLoading.setVisibility(View.GONE);
                        if (swipeRefreshLayout != null) swipeRefreshLayout.setRefreshing(false);
                        showCommandOutput("> tatap$ [ERROR] " + err, true);
                        if (adapter.getItemCount() == 0 && layoutEmptyState != null) {
                            layoutEmptyState.setVisibility(View.VISIBLE);
                            if (rvGrid != null) rvGrid.setVisibility(View.GONE);
                            tvEmptyTitle.setText("Gagal Memuat Data");
                            tvEmptyDesc.setText(err);
                        }
                    });
                }
            } catch (Exception e) {
                runOnUiThread(() -> {
                    if (pbLoading != null) pbLoading.setVisibility(View.GONE);
                    if (swipeRefreshLayout != null) swipeRefreshLayout.setRefreshing(false);
                    showCommandOutput("> tatap$ [ERROR] Gagal terhubung: " + e.getMessage(), true);
                    if (adapter.getItemCount() == 0 && layoutEmptyState != null) {
                        layoutEmptyState.setVisibility(View.VISIBLE);
                        if (rvGrid != null) rvGrid.setVisibility(View.GONE);
                        tvEmptyTitle.setText("Koneksi Terputus");
                        tvEmptyDesc.setText(e.getMessage());
                    }
                });
            }
        }).start();
    }

    private void confirmAndClearHistory() {
        new AlertDialog.Builder(this)
                .setTitle("Hapus Riwayat?")
                .setMessage("Seluruh riwayat anime yang pernah Anda tonton akan dibersihkan.")
                .setPositiveButton("Hapus Semua", (d, w) -> clearWatchHistory())
                .setNegativeButton("Batal", null)
                .show();
    }

    private void clearWatchHistory() {
        showCommandOutput("> tatap$ Menghapus riwayat tontonan...", false);
        new Thread(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL("http://127.0.0.1:8767/api/history").openConnection();
                conn.setRequestMethod("DELETE");
                conn.setConnectTimeout(3000);
                conn.getResponseCode();
                conn.disconnect();

                getSharedPreferences("tatap_history", Context.MODE_PRIVATE).edit().clear().apply();

                runOnUiThread(() -> {
                    showCommandOutput("> tatap$ [OK] Seluruh riwayat tontonan berhasil dibersihkan", false);
                    if ("riwayat".equals(currentView)) {
                        fetchData();
                    }
                });
            } catch (Exception e) {
                runOnUiThread(() -> showCommandOutput("> tatap$ [ERROR] Gagal hapus riwayat: " + e.getMessage(), true));
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
