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
    private String currentView = "musim"; // "musim" | "airing" | "katalog" | "cari"
    private String currentSearchQuery = "";
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
                String query = etSearch.getText().toString().trim();
                if (!query.isEmpty()) {
                    currentView = "cari";
                    currentSearchQuery = query;
                    currentPage = 1;
                    updateTabButtons();
                    fetchData();
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
            } catch (Throwable t) {
                Log.e(TAG, "Error startEmbeddedBackend: " + t.getMessage(), t);
            }
        }).start();
    }

    private void waitForServerAndLoadCatalog(final int attempt) {
        new Thread(() -> {
            boolean ready = false;
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL("http://127.0.0.1:8767/api/ping").openConnection();
                conn.setConnectTimeout(600);
                conn.setReadTimeout(600);
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
            } else if (attempt < 30) {
                try { Thread.sleep(400); } catch (Exception ignored) {}
                waitForServerAndLoadCatalog(attempt + 1);
            } else {
                runOnUiThread(() -> {
                    tvStatusBadge.setText("OFFLINE");
                    tvStatusBadge.setTextColor(0xFFEF4444);
                    Toast.makeText(this, "Server lokal butuh waktu inisialisasi lebih lama, silakan tunggu...", Toast.LENGTH_LONG).show();
                    // Coba muat data langsung siapa tahu baru saja nyala
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
