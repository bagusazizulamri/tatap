package id.tatap.app;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.ImageButton;
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

public class DetailActivity extends Activity {
    private String slug;
    private String title;
    private TextView tvTitle, tvSlug;
    private RecyclerView rvEpisodes;
    private EpisodeAdapter adapter;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_detail);

        slug = getIntent().getStringExtra("slug");
        title = getIntent().getStringExtra("title");

        tvTitle = findViewById(R.id.tv_detail_title);
        tvSlug = findViewById(R.id.tv_detail_slug);
        ImageButton btnBack = findViewById(R.id.btn_back);
        rvEpisodes = findViewById(R.id.rv_episodes);

        tvTitle.setText(title);
        tvSlug.setText("ID: " + slug);

        btnBack.setOnClickListener(v -> finish());

        rvEpisodes.setLayoutManager(new GridLayoutManager(this, 4));
        adapter = new EpisodeAdapter();
        rvEpisodes.setAdapter(adapter);

        loadEpisodes();
    }

    private void loadEpisodes() {
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
                    JSONArray eps = res.getJSONObject("data").getJSONArray("episodes");
                    List<Integer> list = new ArrayList<>();
                    for (int i = 0; i < eps.length(); i++) {
                        list.add(eps.getJSONObject(i).getInt("ep"));
                    }
                    runOnUiThread(() -> {
                        tvSlug.setText(list.size() + " Episode Tersedia");
                        adapter.setEpisodes(list);
                    });
                }
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(this, "Gagal memuat episode: " + e.getMessage(), Toast.LENGTH_SHORT).show());
            }
        }).start();
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
            holder.btnEp.setText("EP " + ep);
            holder.btnEp.setOnClickListener(v -> {
                Intent intent = new Intent(DetailActivity.this, PlayerActivity.class);
                intent.putExtra("slug", slug);
                intent.putExtra("ep", ep);
                intent.putExtra("title", title);
                startActivity(intent);
            });
        }

        @Override
        public int getItemCount() {
            return episodes.size();
        }

        class EpisodeViewHolder extends RecyclerView.ViewHolder {
            Button btnEp;
            public EpisodeViewHolder(@NonNull View itemView) {
                super(itemView);
                btnEp = itemView.findViewById(R.id.btn_ep_num);
            }
        }
    }
}
