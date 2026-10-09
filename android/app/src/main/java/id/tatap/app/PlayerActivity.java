package id.tatap.app;

import android.app.Activity;
import android.content.Context;
import android.media.AudioManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.view.GestureDetector;
import android.view.MotionEvent;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.media3.common.MediaItem;
import androidx.media3.datasource.DefaultHttpDataSource;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.hls.HlsMediaSource;
import androidx.media3.ui.PlayerView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.util.HashMap;
import java.util.Map;

public class PlayerActivity extends Activity {
    private ExoPlayer player;
    private PlayerView playerView;
    private GestureDetector gestureDetector;
    private AudioManager audioManager;
    private View hudOsd;
    private TextView tvOsdIcon, tvOsdVal, tvRippleLeft, tvRippleRight;
    private ProgressBar pbOsdBar;
    private final Handler handler = new Handler(Looper.getMainLooper());

    private String slug;
    private int ep;
    private String title;
    private float currentBrightness = 0.5f;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN, WindowManager.LayoutParams.FLAG_FULLSCREEN);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        setContentView(R.layout.activity_player);

        slug = getIntent().getStringExtra("slug");
        ep = getIntent().getIntExtra("ep", 1);
        title = getIntent().getStringExtra("title");

        playerView = findViewById(R.id.player_view);
        hudOsd = findViewById(R.id.hud_osd);
        tvOsdIcon = findViewById(R.id.tv_osd_icon);
        tvOsdVal = findViewById(R.id.tv_osd_val);
        pbOsdBar = findViewById(R.id.pb_osd_bar);
        tvRippleLeft = findViewById(R.id.tv_ripple_left);
        tvRippleRight = findViewById(R.id.tv_ripple_right);

        audioManager = (AudioManager) getSystemService(Context.AUDIO_SERVICE);

        initExoPlayer();
        setupGestureControls();
        resolveAndPlayStream();
    }

    private void initExoPlayer() {
        player = new ExoPlayer.Builder(this).build();
        playerView.setPlayer(player);
    }

    private void setupGestureControls() {
        gestureDetector = new GestureDetector(this, new GestureDetector.SimpleOnGestureListener() {
            @Override
            public boolean onDoubleTap(MotionEvent e) {
                float screenWidth = playerView.getWidth();
                float x = e.getX();

                if (x < screenWidth * 0.35f) {
                    seekRelative(-10000);
                    showRipple(tvRippleLeft);
                } else if (x > screenWidth * 0.65f) {
                    seekRelative(10000);
                    showRipple(tvRippleRight);
                } else {
                    if (player.isPlaying()) {
                        player.pause();
                    } else {
                        player.play();
                    }
                }
                vibrate(25);
                return true;
            }

            @Override
            public boolean onScroll(MotionEvent e1, MotionEvent e2, float distanceX, float distanceY) {
                if (e1 == null || e2 == null) return false;
                float deltaY = e1.getY() - e2.getY();
                float screenWidth = playerView.getWidth();

                if (Math.abs(distanceY) > Math.abs(distanceX)) {
                    if (e1.getX() < screenWidth * 0.5f) {
                        adjustBrightness(distanceY / playerView.getHeight());
                    } else {
                        adjustVolume(distanceY / playerView.getHeight());
                    }
                    return true;
                }
                return false;
            }
        });

        playerView.setOnTouchListener((v, event) -> {
            gestureDetector.onTouchEvent(event);
            return false;
        });
    }

    private void seekRelative(long deltaMs) {
        if (player != null) {
            long newPos = Math.max(0, Math.min(player.getDuration(), player.getCurrentPosition() + deltaMs));
            player.seekTo(newPos);
        }
    }

    private void adjustVolume(float percent) {
        int maxVol = audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC);
        int curVol = audioManager.getStreamVolume(AudioManager.STREAM_MUSIC);
        int step = (int) (percent * maxVol * 1.5f);
        int newVol = Math.max(0, Math.min(maxVol, curVol + step));
        audioManager.setStreamVolume(AudioManager.STREAM_MUSIC, newVol, 0);

        int pct = (int) ((newVol / (float) maxVol) * 100);
        showOsd(newVol == 0 ? "🔇" : "🔊", pct);
    }

    private void adjustBrightness(float percent) {
        currentBrightness = Math.max(0.05f, Math.min(1.0f, currentBrightness + (percent * 1.2f)));
        WindowManager.LayoutParams lp = getWindow().getAttributes();
        lp.screenBrightness = currentBrightness;
        getWindow().setAttributes(lp);

        int pct = (int) (currentBrightness * 100);
        showOsd("☀️", pct);
    }

    private void showOsd(String icon, int pct) {
        tvOsdIcon.setText(icon);
        pbOsdBar.setProgress(pct);
        tvOsdVal.setText(pct + "%");
        hudOsd.setVisibility(View.VISIBLE);
        handler.removeCallbacks(hideOsdRunnable);
        handler.postDelayed(hideOsdRunnable, 1200);
    }

    private final Runnable hideOsdRunnable = () -> hudOsd.setVisibility(View.GONE);

    private void showRipple(TextView tv) {
        tv.setVisibility(View.VISIBLE);
        handler.postDelayed(() -> tv.setVisibility(View.GONE), 350);
    }

    private void vibrate(long ms) {
        Vibrator v = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
        if (v != null && v.hasVibrator()) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                v.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE));
            } else {
                v.vibrate(ms);
            }
        }
    }

    private void resolveAndPlayStream() {
        new Thread(() -> {
            try {
                String u = "http://127.0.0.1:8767/api/stream/resolve?slug=" + URLEncoder.encode(slug, "UTF-8")
                        + "&ep=" + ep + "&mode=sub&q=best";
                HttpURLConnection conn = (HttpURLConnection) new URL(u).openConnection();
                conn.setConnectTimeout(15000);
                conn.setReadTimeout(20000);
                BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) sb.append(line);
                reader.close();

                JSONObject res = new JSONObject(sb.toString());
                if (res.optBoolean("success")) {
                    JSONObject data = res.getJSONObject("data");
                    String streamUrl = "";
                    if (data.has("picked")) {
                        streamUrl = data.getJSONObject("picked").optString("url");
                    } else if (data.has("variants")) {
                        JSONArray vars = data.getJSONArray("variants");
                        if (vars.length() > 0) {
                            streamUrl = vars.getJSONObject(0).optString("url");
                        }
                    }
                    String referer = data.optString("referer", "");

                    if (!streamUrl.isEmpty()) {
                        final String finalUrl = streamUrl;
                        final String finalRef = referer;
                        runOnUiThread(() -> playHls(finalUrl, finalRef));
                    }
                } else {
                    runOnUiThread(() -> Toast.makeText(this, "Gagal resolve: " + res.optString("error"), Toast.LENGTH_LONG).show());
                }
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(this, "Error streaming: " + e.getMessage(), Toast.LENGTH_SHORT).show());
            }
        }).start();
    }

    private void playHls(String streamUrl, String referer) {
        // Melalui proxy local Tatap agar bypass TLS desync / DPI ISP berfungsi transparan
        String proxiedUrl = "http://127.0.0.1:8767/api/player/video?url=" + Uri.encode(streamUrl)
                + "&referer=" + Uri.encode(referer);

        Map<String, String> headers = new HashMap<>();
        if (!referer.isEmpty()) {
            headers.put("Referer", referer);
        }

        DefaultHttpDataSource.Factory httpDataSourceFactory = new DefaultHttpDataSource.Factory()
                .setDefaultRequestProperties(headers)
                .setUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0");

        HlsMediaSource mediaSource = new HlsMediaSource.Factory(httpDataSourceFactory)
                .createMediaSource(MediaItem.fromUri(Uri.parse(proxiedUrl)));

        player.setMediaSource(mediaSource);
        player.prepare();
        player.play();
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (player != null) player.pause();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (player != null) {
            player.release();
            player = null;
        }
    }
}
