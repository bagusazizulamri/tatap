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

        holder.tvTitle.setText(title);
        holder.tvMeta.setText((type.isEmpty() ? "" : type + " · ") + (eps.isEmpty() ? "" : eps + " Ep"));
        holder.tvBadgeEp.setText(sub.isEmpty() ? "ANIME" : "SUB " + sub);

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
        TextView tvTitle, tvMeta, tvBadgeEp;

        public AnimeViewHolder(@NonNull View itemView) {
            super(itemView);
            ivPoster = itemView.findViewById(R.id.iv_poster);
            tvTitle = itemView.findViewById(R.id.tv_title);
            tvMeta = itemView.findViewById(R.id.tv_meta);
            tvBadgeEp = itemView.findViewById(R.id.tv_badge_ep);
        }
    }
}
