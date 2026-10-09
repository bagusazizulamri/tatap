package id.tatap.app;

import android.app.Activity;
import android.content.Context;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputMethodManager;
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
    private EditText etSearch;
    private ProgressBar pbLoading;
    private TextView tvSectionTitle, tvItemCount, tvStatusBadge;
    private RecyclerView rvGrid;
    private AnimeAdapter adapter;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        etSearch = findViewById(R.id.et_search);
        pbLoading = findViewById(R.id.pb_loading);
        tvSectionTitle = findViewById(R.id.tv_section_title);
        tvItemCount = findViewById(R.id.tv_item_count);
        tvStatusBadge = findViewById(R.id.tv_status_badge);
        rvGrid = findViewById(R.id.rv_anime_grid);

        rvGrid.setLayoutManager(new GridLayoutManager(this, 2));
        adapter = new AnimeAdapter(this);
        rvGrid.setAdapter(adapter);

        etSearch.setOnEditorActionListener((v, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_SEARCH ||
                    (event != null && event.getKeyCode() == KeyEvent.KEYCODE_ENTER && event.getAction() == KeyEvent.ACTION_DOWN)) {
                hideKeyboard();
                String query = etSearch.getText().toString().trim();
                if (!query.isEmpty()) {
                    searchAnime(query);
                }
                return true;
            }
            return false;
        });

        // Nyalakan backend Python lokal
        startEmbeddedBackend();

        // Tunggu server lokal siap lalu muat katalog seasonal awal
        waitForServerAndLoadCatalog(0);
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
                Class<?> pyClass = Class.forName("com.chaquo.python.Python");
                if (!(Boolean) pyClass.getMethod("isStarted").invoke(null)) {
                    Class<?> androidPlatform = Class.forName("com.chaquo.python.android.AndroidPlatform");
                    Object platform = androidPlatform.getConstructor(Context.class).newInstance(getApplicationContext());
                    pyClass.getMethod("start", Class.forName("com.chaquo.python.Platform")).invoke(null, platform);
                }
                Object pyInstance = pyClass.getMethod("getInstance").invoke(null);
                Object launcherMod = pyClass.getMethod("getModule", String.class).invoke(pyInstance, "server_launcher");
                String dataDir = getFilesDir().getAbsolutePath();
                launcherMod.getClass().getMethod("callAttr", String.class, Object[].class).invoke(launcherMod, "run_in_background", new Object[]{dataDir});
            } catch (Throwable t) {
                t.printStackTrace();
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
                    loadSeasonalAnime();
                });
            } else if (attempt < 20) {
                try { Thread.sleep(300); } catch (Exception ignored) {}
                waitForServerAndLoadCatalog(attempt + 1);
            } else {
                runOnUiThread(() -> {
                    tvStatusBadge.setText("OFFLINE");
                    tvStatusBadge.setTextColor(0xFFEF4444);
                    Toast.makeText(this, "Server backend lokal sedang bersiap...", Toast.LENGTH_SHORT).show();
                });
            }
        }).start();
    }

    private void loadSeasonalAnime() {
        pbLoading.setVisibility(View.VISIBLE);
        tvSectionTitle.setText("Tayang Musim Ini");
        new Thread(() -> {
            try {
                String u = "http://127.0.0.1:8767/api/seasonal?which=now&page=1";
                HttpURLConnection conn = (HttpURLConnection) new URL(u).openConnection();
                conn.setConnectTimeout(10000);
                conn.setReadTimeout(10000);
                BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) sb.append(line);
                reader.close();

                JSONObject res = new JSONObject(sb.toString());
                if (res.optBoolean("success")) {
                    JSONArray arr = res.getJSONObject("data").getJSONArray("results");
                    List<JSONObject> list = new ArrayList<>();
                    for (int i = 0; i < arr.length(); i++) {
                        list.add(arr.getJSONObject(i));
                    }
                    runOnUiThread(() -> {
                        pbLoading.setVisibility(View.GONE);
                        tvItemCount.setText(list.size() + " judul");
                        adapter.setData(list);
                    });
                }
            } catch (Exception e) {
                runOnUiThread(() -> {
                    pbLoading.setVisibility(View.GONE);
                    Toast.makeText(this, "Gagal memuat katalog: " + e.getMessage(), Toast.LENGTH_SHORT).show();
                });
            }
        }).start();
    }

    private void searchAnime(String query) {
        pbLoading.setVisibility(View.VISIBLE);
        tvSectionTitle.setText("Hasil Pencarian: " + query);
        new Thread(() -> {
            try {
                String u = "http://127.0.0.1:8767/api/search?q=" + URLEncoder.encode(query, "UTF-8") + "&limit=20";
                HttpURLConnection conn = (HttpURLConnection) new URL(u).openConnection();
                conn.setConnectTimeout(10000);
                conn.setReadTimeout(10000);
                BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) sb.append(line);
                reader.close();

                JSONObject res = new JSONObject(sb.toString());
                if (res.optBoolean("success")) {
                    JSONArray arr = res.getJSONObject("data").getJSONArray("results");
                    List<JSONObject> list = new ArrayList<>();
                    for (int i = 0; i < arr.length(); i++) {
                        list.add(arr.getJSONObject(i));
                    }
                    runOnUiThread(() -> {
                        pbLoading.setVisibility(View.GONE);
                        tvItemCount.setText(list.size() + " judul");
                        adapter.setData(list);
                    });
                }
            } catch (Exception e) {
                runOnUiThread(() -> {
                    pbLoading.setVisibility(View.GONE);
                    Toast.makeText(this, "Gagal mencari: " + e.getMessage(), Toast.LENGTH_SHORT).show();
                });
            }
        }).start();
    }
}
