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

import android.app.AlertDialog;
import android.graphics.Color;
import android.graphics.Typeface;
import android.util.TypedValue;
import android.widget.Button;
import android.widget.ImageButton;

import androidx.media3.common.C;
import androidx.media3.common.Format;
import androidx.media3.common.MediaItem;
import androidx.media3.common.MimeTypes;
import androidx.media3.datasource.DefaultHttpDataSource;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.hls.HlsMediaSource;
import androidx.media3.exoplayer.source.MergingMediaSource;
import androidx.media3.exoplayer.source.SingleSampleMediaSource;
import androidx.media3.ui.CaptionStyleCompat;
import androidx.media3.ui.PlayerView;
import androidx.media3.ui.SubtitleView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class PlayerActivity extends Activity {
    private ExoPlayer player;
    private PlayerView playerView;
    private GestureDetector gestureDetector;
    private AudioManager audioManager;
    private View hudOsd;
    private TextView tvOsdIcon, tvOsdVal, tvRippleLeft, tvRippleRight;
    private ProgressBar pbOsdBar;
    private TextView tvPlayerTitle, tvSubStatus;
    private Button btnSubSelector;
    private ImageButton btnPlayerBack;
    private View layoutTopBar;
    private final Handler handler = new Handler(Looper.getMainLooper());

    private String slug;
    private int ep;
    private String title;
    private float currentBrightness = 0.5f;

    // Subtitle Engine State
    private String rawStreamUrl = "";
    private String streamReferer = "";
    private List<JSONObject> subtitleTracks = new ArrayList<>();
    private String activeSubUrl = "";
    private String activeSubLang = "id"; // Default Indonesian
    private String activeEngine = "aigtx"; // "aigtx" | "gtx" | "ai" | "raw"
    private boolean subEnabled = true;

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

        layoutTopBar = findViewById(R.id.layout_top_bar);
        tvPlayerTitle = findViewById(R.id.tv_player_title);
        tvSubStatus = findViewById(R.id.tv_sub_status);
        btnSubSelector = findViewById(R.id.btn_sub_selector);
        btnPlayerBack = findViewById(R.id.btn_player_back);

        if (title != null && !title.isEmpty()) {
            tvPlayerTitle.setText(title + " - Ep " + ep);
        } else {
            tvPlayerTitle.setText("Episode " + ep);
        }

        btnPlayerBack.setOnClickListener(v -> finish());
        btnSubSelector.setOnClickListener(v -> showSubtitleSelectorDialog());

        audioManager = (AudioManager) getSystemService(Context.AUDIO_SERVICE);

        initExoPlayer();
        setupGestureControls();
        resolveAndPlayStream();
    }

    private void initExoPlayer() {
        player = new ExoPlayer.Builder(this).build();
        playerView.setPlayer(player);

        // Styling native SubtitleView agar tajam dengan outline hitam kontras
        SubtitleView subView = playerView.getSubtitleView();
        if (subView != null) {
            subView.setApplyEmbeddedStyles(false);
            subView.setApplyEmbeddedFontSizes(false);
            subView.setFixedTextSize(TypedValue.COMPLEX_UNIT_SP, 19f);
            subView.setBottomPaddingFraction(0.08f);

            CaptionStyleCompat style = new CaptionStyleCompat(
                    Color.WHITE,
                    Color.argb(160, 0, 0, 0),
                    Color.TRANSPARENT,
                    CaptionStyleCompat.EDGE_TYPE_OUTLINE,
                    Color.BLACK,
                    Typeface.DEFAULT_BOLD
            );
            subView.setStyle(style);
        }
    }

    private void setupGestureControls() {
        gestureDetector = new GestureDetector(this, new GestureDetector.SimpleOnGestureListener() {
            @Override
            public boolean onSingleTapConfirmed(MotionEvent e) {
                // Toggle visibility top bar
                if (layoutTopBar.getVisibility() == View.VISIBLE) {
                    layoutTopBar.setVisibility(View.GONE);
                } else {
                    layoutTopBar.setVisibility(View.VISIBLE);
                    handler.postDelayed(() -> {
                        if (player != null && player.isPlaying()) {
                            layoutTopBar.setVisibility(View.GONE);
                        }
                    }, 4000);
                }
                return true;
            }

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

                    // Simpan subtitle tracks yang tersedia
                    JSONArray subArr = data.optJSONArray("subtitles");
                    subtitleTracks.clear();
                    String enSub = "";
                    if (subArr != null) {
                        for (int i = 0; i < subArr.length(); i++) {
                            JSONObject s = subArr.getJSONObject(i);
                            subtitleTracks.add(s);
                            String lang = s.optString("lang", "").toLowerCase();
                            String lbl = s.optString("label", "").toLowerCase();
                            if (enSub.isEmpty() && (lang.equals("en") || lbl.contains("english"))) {
                                enSub = s.optString("url", "");
                            }
                        }
                    }
                    if (enSub.isEmpty() && !subtitleTracks.isEmpty()) {
                        enSub = subtitleTracks.get(0).optString("url", "");
                    }
                    activeSubUrl = enSub;
                    rawStreamUrl = streamUrl;
                    streamReferer = referer;

                    if (!rawStreamUrl.isEmpty()) {
                        runOnUiThread(this::applyCurrentStreamAndSubtitles);
                    }
                } else {
                    runOnUiThread(() -> Toast.makeText(this, "Gagal resolve: " + res.optString("error"), Toast.LENGTH_LONG).show());
                }
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(this, "Error streaming: " + e.getMessage(), Toast.LENGTH_SHORT).show());
            }
        }).start();
    }

    private void applyCurrentStreamAndSubtitles() {
        if (rawStreamUrl.isEmpty()) return;

        long currentPosition = player != null ? player.getCurrentPosition() : 0;
        boolean wasPlaying = player != null && player.isPlaying();

        String proxiedVideo = "http://127.0.0.1:8767/api/player/video?url=" + Uri.encode(rawStreamUrl)
                + "&referer=" + Uri.encode(streamReferer);

        Map<String, String> headers = new HashMap<>();
        if (!streamReferer.isEmpty()) {
            headers.put("Referer", streamReferer);
        }

        DefaultHttpDataSource.Factory httpDataSourceFactory = new DefaultHttpDataSource.Factory()
                .setDefaultRequestProperties(headers)
                .setUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0");

        HlsMediaSource videoSource = new HlsMediaSource.Factory(httpDataSourceFactory)
                .createMediaSource(MediaItem.fromUri(Uri.parse(proxiedVideo)));

        if (subEnabled && !activeSubUrl.isEmpty()) {
            // Bangun URL subtitle yang diarahkan ke backend translation proxy
            String subModeParam = activeEngine.equals("raw") ? "" : activeEngine;
            String proxiedSub = "http://127.0.0.1:8767/api/player/sub?url=" + Uri.encode(activeSubUrl)
                    + "&referer=" + Uri.encode(streamReferer)
                    + "&src=en&lang=" + Uri.encode(activeSubLang)
                    + (subModeParam.isEmpty() ? "" : "&mode=" + subModeParam);

            Format textFormat = new Format.Builder()
                    .setSampleMimeType(MimeTypes.TEXT_VTT)
                    .setLanguage(activeSubLang)
                    .setSelectionFlags(C.SELECTION_FLAG_DEFAULT)
                    .build();

            SingleSampleMediaSource subSource = new SingleSampleMediaSource.Factory(httpDataSourceFactory)
                    .createMediaSource(new MediaItem.SubtitleConfiguration.Builder(Uri.parse(proxiedSub))
                            .setMimeType(MimeTypes.TEXT_VTT)
                            .setLanguage(activeSubLang)
                            .setSelectionFlags(C.SELECTION_FLAG_DEFAULT)
                            .build(), C.TIME_UNSET);

            MergingMediaSource merged = new MergingMediaSource(true, true, videoSource, subSource);
            player.setMediaSource(merged);

            String engineLabel = "AIGTX (Cepat)";
            if ("gtx".equals(activeEngine)) engineLabel = "Google GTX";
            else if ("ai".equals(activeEngine)) engineLabel = "AI Fansub LLM";
            else if ("raw".equals(activeEngine)) engineLabel = "Source English";

            tvSubStatus.setText("Sub: " + activeSubLang.toUpperCase() + " • " + engineLabel);
        } else {
            player.setMediaSource(videoSource);
            tvSubStatus.setText("Subtitle: Nonaktif");
        }

        player.prepare();
        if (currentPosition > 0) {
            player.seekTo(currentPosition);
        }
        player.play();
    }

    private void showSubtitleSelectorDialog() {
        AlertDialog.Builder builder = new AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert);
        builder.setTitle("Pengaturan Subtitle & Mesin Terjemahan");

        String[] options = new String[]{
                "🇮🇩 Bahasa Indonesia (AIGTX - Instan & Cerdas)" + (subEnabled && "id".equals(activeSubLang) && "aigtx".equals(activeEngine) ? " ✓" : ""),
                "🇮🇩 Bahasa Indonesia (AI Fansub LLM / Gemini)" + (subEnabled && "id".equals(activeSubLang) && "ai".equals(activeEngine) ? " ✓" : ""),
                "🇮🇩 Bahasa Indonesia (Google GTX Murni)" + (subEnabled && "id".equals(activeSubLang) && "gtx".equals(activeEngine) ? " ✓" : ""),
                "🇬🇧 English (Original / Asli)" + (subEnabled && "en".equals(activeSubLang) ? " ✓" : ""),
                "❌ Matikan Subtitle" + (!subEnabled ? " ✓" : "")
        };

        builder.setItems(options, (dialog, which) -> {
            switch (which) {
                case 0:
                    subEnabled = true;
                    activeSubLang = "id";
                    activeEngine = "aigtx";
                    break;
                case 1:
                    subEnabled = true;
                    activeSubLang = "id";
                    activeEngine = "ai";
                    break;
                case 2:
                    subEnabled = true;
                    activeSubLang = "id";
                    activeEngine = "gtx";
                    break;
                case 3:
                    subEnabled = true;
                    activeSubLang = "en";
                    activeEngine = "raw";
                    break;
                case 4:
                    subEnabled = false;
                    break;
            }
            applyCurrentStreamAndSubtitles();
            Toast.makeText(this, "Subtitle diperbarui: " + (subEnabled ? activeSubLang.toUpperCase() + " [" + activeEngine + "]" : "OFF"), Toast.LENGTH_SHORT).show();
        });

        builder.setNegativeButton("Tutup", (dialog, which) -> dialog.dismiss());
        builder.show();
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
