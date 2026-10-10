package id.tatap.app;

import android.content.Context;
import android.content.Intent;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class AnimeAdapter extends RecyclerView.Adapter<AnimeAdapter.AnimeViewHolder> {
    private final Context context;
    private final List<JSONObject> items = new ArrayList<>();

    public AnimeAdapter(Context context) {
        this.context = context;
    }

    public void setData(List<JSONObject> newItems) {
        items.clear();
        if (newItems != null) {
            items.addAll(newItems);
        }
        notifyDataSetChanged();
    }

    @NonNull
    @Override
    public AnimeViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(context).inflate(R.layout.item_anime_card, parent, false);
        return new AnimeViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull AnimeViewHolder holder, int position) {
        JSONObject item = items.get(position);
        String title = item.optString("title", "Tanpa Judul");
        String poster = item.optString("poster", "");
        String sub = item.optString("sub", "");
        String type = item.optString("type", "");
        String eps = item.optString("eps", "");
        String slug = item.optString("id", item.optString("slug", ""));
        double score = item.optDouble("score", 0.0);
        String duration = item.optString("duration", "");

        holder.tvTitle.setText(title);

        // Format Format/Type Badge (TV, Movie, ONA)
        if (!type.isEmpty()) {
            holder.tvBadgeType.setVisibility(View.VISIBLE);
            holder.tvBadgeType.setText(type.toUpperCase());
        } else {
            holder.tvBadgeType.setVisibility(View.GONE);
        }

        // Format Score Badge (★ 8.5)
        if (score > 0) {
            holder.tvBadgeScore.setVisibility(View.VISIBLE);
            holder.tvBadgeScore.setText(String.format(Locale.US, "★ %.1f", score));
        } else {
            holder.tvBadgeScore.setVisibility(View.GONE);
        }

        // Format Subtitle / Status Badge
        if (!sub.isEmpty()) {
            holder.tvBadgeEp.setText("SUB " + sub.toUpperCase());
        } else if (!eps.isEmpty() && !eps.equals("0")) {
            holder.tvBadgeEp.setText("EP " + eps);
        } else {
            holder.tvBadgeEp.setText("ANIME");
        }

        // Format Meta Info
        StringBuilder metaStr = new StringBuilder();
        if (!eps.isEmpty() && !eps.equals("0")) {
            metaStr.append(eps).append(" Ep");
        }
        if (!duration.isEmpty()) {
            if (metaStr.length() > 0) metaStr.append(" · ");
            metaStr.append(duration);
        }
        if (metaStr.length() == 0 && !type.isEmpty()) {
            metaStr.append(type);
        }
        holder.tvMeta.setText(metaStr.length() > 0 ? metaStr.toString() : "Tatap Anime");

        ImageLoader.load(poster, holder.ivPoster);

        holder.itemView.setOnClickListener(v -> {
            Intent intent = new Intent(context, DetailActivity.class);
            intent.putExtra("slug", slug);
            intent.putExtra("title", title);
            intent.putExtra("poster", poster);
            intent.putExtra("type", type);
            intent.putExtra("eps", eps);
            intent.putExtra("sub", sub);
            context.startActivity(intent);
        });
    }

    @Override
    public int getItemCount() {
        return items.size();
    }

    public static class AnimeViewHolder extends RecyclerView.ViewHolder {
        ImageView ivPoster;
        TextView tvTitle, tvMeta, tvBadgeEp, tvBadgeScore, tvBadgeType;

        public AnimeViewHolder(@NonNull View itemView) {
            super(itemView);
            ivPoster = itemView.findViewById(R.id.iv_poster);
            tvTitle = itemView.findViewById(R.id.tv_title);
            tvMeta = itemView.findViewById(R.id.tv_meta);
            tvBadgeEp = itemView.findViewById(R.id.tv_badge_ep);
            tvBadgeScore = itemView.findViewById(R.id.tv_badge_score);
            tvBadgeType = itemView.findViewById(R.id.tv_badge_type);
        }
    }
}
