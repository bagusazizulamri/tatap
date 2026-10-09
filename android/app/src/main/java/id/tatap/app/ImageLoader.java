package id.tatap.app;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Handler;
import android.os.Looper;
import android.util.LruCache;
import android.widget.ImageView;

import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ImageLoader {
    private static final ExecutorService executor = Executors.newFixedThreadPool(4);
    private static final Handler mainHandler = new Handler(Looper.getMainLooper());
    private static final LruCache<String, Bitmap> memoryCache;

    static {
        final int maxMemory = (int) (Runtime.getRuntime().maxMemory() / 1024);
        final int cacheSize = maxMemory / 8;
        memoryCache = new LruCache<String, Bitmap>(cacheSize) {
            @Override
            protected int sizeOf(String key, Bitmap bitmap) {
                return bitmap.getByteCount() / 1024;
            }
        };
    }

    public static void load(final String urlString, final ImageView imageView) {
        if (urlString == null || urlString.isEmpty()) {
            imageView.setImageDrawable(null);
            return;
        }

        Bitmap cached = memoryCache.get(urlString);
        if (cached != null) {
            imageView.setImageBitmap(cached);
            return;
        }

        imageView.setTag(urlString);
        executor.execute(() -> {
            try {
                URL url = new URL(urlString);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setConnectTimeout(8000);
                conn.setReadTimeout(8000);
                conn.setRequestProperty("User-Agent", "Mozilla/5.0");
                conn.connect();
                InputStream input = conn.getInputStream();
                Bitmap bitmap = BitmapFactory.decodeStream(input);
                if (bitmap != null) {
                    memoryCache.put(urlString, bitmap);
                    mainHandler.post(() -> {
                        if (urlString.equals(imageView.getTag())) {
                            imageView.setImageBitmap(bitmap);
                        }
                    });
                }
                conn.disconnect();
            } catch (Exception ignored) {}
        });
    }
}
