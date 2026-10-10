package id.tatap.app;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.cardview.widget.CardView;
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
import java.util.Collections;
import java.util.List;

public class DetailActivity extends Activity {
    private String slug;
    private String title;
    private String poster;
    private String type;
    private String eps;
    private String sub;

    private TextView tvTitle, tvTitleFull, tvSlug, tvTypeBadge;
    private ImageView ivPoster;
    private Button btnQuickPlay, btnSortOrder;
    private ProgressBar pbLoading;
    private RecyclerView rvEpisodes;
    private EpisodeAdapter adapter;

    private SharedPreferences prefs;
    private final List<Integer> originalEpisodes = new ArrayList<>();
    private boolean isAscending = true;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_detail);

        slug = getIntent().getStringExtra("slug");
        title = getIntent().getStringExtra("title");
        poster = getIntent().getStringExtra("poster");
        type = getIntent().getStringExtra("type");
        eps = getIntent().getStringExtra("eps");
        sub = getIntent().getStringExtra("sub");

        prefs = getSharedPreferences("tatap_history", Context.MODE_PRIVATE);

        tvTitle = findViewById(R.id.tv_detail_title);
        tvTitleFull = findViewById(R.id.tv_detail_title_full);
        tvSlug = findViewById(R.id.tv_detail_slug);
        tvTypeBadge = findViewById(R.id.tv_detail_type_badge);
        ivPoster = findViewById(R.id.iv_detail_poster);
        btnQuickPlay = findViewById(R.id.btn_quick_play);
        btnSortOrder = findViewById(R.id.btn_sort_order);
        pbLoading = findViewById(R.id.pb_detail_loading);
        ImageButton btnBack = findViewById(R.id.btn_back);
        rvEpisodes = findViewById(R.id.rv_episodes);

        tvTitle.setText(title != null ? title : "Detail Anime");
        tvTitleFull.setText(title != null ? title : "Anime");

        String badgeText = (type != null && !type.isEmpty() ? type : "ANIME")
                + (eps != null && !eps.isEmpty() ? " · " + eps + " EP" : "")
                + (sub != null && !sub.isEmpty() ? " · " + sub : "");
        tvTypeBadge.setText(badgeText);
        tvSlug.setText("Memuat episode...");

        if (poster != null && !poster.isEmpty()) {
            ImageLoader.load(poster, ivPoster);
        }

        btnBack.setOnClickListener(v -> finish());

        int epSpan = getResources().getInteger(R.integer.episode_grid_columns);
        rvEpisodes.setLayoutManager(new GridLayoutManager(this, epSpan));
        adapter = new EpisodeAdapter();
        rvEpisodes.setAdapter(adapter);

        btnSortOrder.setOnClickListener(v -> {
            isAscending = !isAscending;
            btnSortOrder.setText(isAscending ? "1 ➔ N" : "N ➔ 1");
            updateEpisodeDisplay();
        });

        btnQuickPlay.setOnClickListener(v -> {
            int targetEp = prefs.getInt("last_ep_" + slug, -1);
            if (targetEp <= 0) {
                if (!originalEpisodes.isEmpty()) {
                    targetEp = originalEpisodes.get(0);
                } else {
                    targetEp = 1;
                }
            }
            playEpisode(targetEp);
        });

        updateQuickPlayButton();
        loadEpisodes();
    }

    @Override
    protected void onResume() {
        super.onResume();
        updateQuickPlayButton();
        if (adapter != null) {
            adapter.notifyDataSetChanged();
        }
    }

    private void updateQuickPlayButton() {
        int lastEp = prefs.getInt("last_ep_" + slug, -1);
        if (lastEp > 0) {
            btnQuickPlay.setText("▶ Lanjutkan Ep " + lastEp);
            btnQuickPlay.setBackgroundColor(0xFF1E2433);
        } else {
            btnQuickPlay.setText("▶ Putar Ep 1");
            btnQuickPlay.setBackgroundColor(0xFF161922);
        }
    }

    private void playEpisode(int ep) {
        prefs.edit()
                .putInt("last_ep_" + slug, ep)
                .putBoolean("watched_" + slug + "_" + ep, true)
                .apply();

        // Rekam riwayat tontonan ke backend lokal
        new Thread(() -> {
            try {
                JSONObject b = new JSONObject();
                b.put("slug", slug);
                b.put("title", title != null ? title : slug);
                b.put("episode", ep);
                b.put("poster", poster != null ? poster : "");
                b.put("type", type != null ? type : "");
                b.put("mode", "sub");

                HttpURLConnection conn = (HttpURLConnection) new URL("http://127.0.0.1:8767/api/history").openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setDoOutput(true);
                conn.setConnectTimeout(3000);
                java.io.OutputStream os = conn.getOutputStream();
                os.write(b.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));
                os.close();
                conn.getResponseCode();
                conn.disconnect();
            } catch (Exception ignored) {}
        }).start();

        Intent intent = new Intent(DetailActivity.this, PlayerActivity.class);
        intent.putExtra("slug", slug);
        intent.putExtra("ep", ep);
        intent.putExtra("title", title);
        intent.putExtra("poster", poster);
        intent.putExtra("type", type);
        startActivity(intent);
    }

    private void loadEpisodes() {
        if (pbLoading != null) pbLoading.setVisibility(View.VISIBLE);
        new Thread(() -> {
            try {
                String u = "http://127.0.0.1:8767/api/anime/" + URLEncoder.encode(slug, "UTF-8") + "/episodes";
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
                    JSONArray epsArr = res.getJSONObject("data").getJSONArray("episodes");
                    List<Integer> list = new ArrayList<>();
                    for (int i = 0; i < epsArr.length(); i++) {
                        list.add(epsArr.getJSONObject(i).getInt("ep"));
                    }
                    Collections.sort(list);
                    runOnUiThread(() -> {
                        if (pbLoading != null) pbLoading.setVisibility(View.GONE);
                        originalEpisodes.clear();
                        originalEpisodes.addAll(list);
                        tvSlug.setText(list.size() + " Episode Tersedia");
                        updateEpisodeDisplay();
                        updateQuickPlayButton();
                    });
                } else {
                    runOnUiThread(() -> {
                        if (pbLoading != null) pbLoading.setVisibility(View.GONE);
                        tvSlug.setText("Episode tidak ditemukan");
                    });
                }
            } catch (Exception e) {
                runOnUiThread(() -> {
                    if (pbLoading != null) pbLoading.setVisibility(View.GONE);
                    Toast.makeText(this, "Gagal memuat episode: " + e.getMessage(), Toast.LENGTH_SHORT).show();
                    tvSlug.setText("Gagal terhubung ke backend");
                });
            }
        }).start();
    }

    private void updateEpisodeDisplay() {
        List<Integer> displayList = new ArrayList<>(originalEpisodes);
        if (!isAscending) {
            Collections.reverse(displayList);
        }
        adapter.setEpisodes(displayList);
    }

    class EpisodeAdapter extends RecyclerView.Adapter<EpisodeAdapter.EpisodeViewHolder> {
        private final List<Integer> episodes = new ArrayList<>();

        public void setEpisodes(List<Integer> list) {
            episodes.clear();
            if (list != null) episodes.addAll(list);
            notifyDataSetChanged();
        }

        @NonNull
        @Override
        public EpisodeViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
            View view = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_episode, parent, false);
            return new EpisodeViewHolder(view);
        }

        @Override
        public void onBindViewHolder(@NonNull EpisodeViewHolder holder, int position) {
            int ep = episodes.get(position);
            holder.tvTitle.setText(String.format("EP %02d", ep));

            int lastPlayedEp = prefs.getInt("last_ep_" + slug, -1);
            boolean isWatched = prefs.getBoolean("watched_" + slug + "_" + ep, false);

            if (ep == lastPlayedEp) {
                // Last played episode
                holder.card.setCardBackgroundColor(0xFF1C2230);
                holder.tvTitle.setTextColor(0xFF38BDF8);
                holder.tvBadge.setVisibility(View.VISIBLE);
                holder.tvBadge.setText("▶ TERAKHIR");
                holder.tvBadge.setTextColor(0xFF38BDF8);
            } else if (isWatched) {
                // Watched episode
                holder.card.setCardBackgroundColor(0xFF0E1017);
                holder.tvTitle.setTextColor(0xFF64748B);
                holder.tvBadge.setVisibility(View.VISIBLE);
                holder.tvBadge.setText("✓ DITONTON");
                holder.tvBadge.setTextColor(0xFF10B981);
            } else {
                // Unwatched episode
                holder.card.setCardBackgroundColor(0xFF11141C);
                holder.tvTitle.setTextColor(0xFFF1F5F9);
                holder.tvBadge.setVisibility(View.GONE);
            }

            holder.itemView.setOnClickListener(v -> playEpisode(ep));
        }

        @Override
        public int getItemCount() {
            return episodes.size();
        }

        class EpisodeViewHolder extends RecyclerView.ViewHolder {
            CardView card;
            TextView tvTitle;
            TextView tvBadge;

            public EpisodeViewHolder(@NonNull View itemView) {
                super(itemView);
                card = itemView.findViewById(R.id.card_episode);
                tvTitle = itemView.findViewById(R.id.tv_ep_title);
                tvBadge = itemView.findViewById(R.id.tv_ep_status_badge);
            }
        }
    }
}
