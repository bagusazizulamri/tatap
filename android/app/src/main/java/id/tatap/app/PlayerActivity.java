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
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.util.TypedValue;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.ImageButton;

import androidx.media3.common.C;
import androidx.media3.common.Format;
import androidx.media3.common.MediaItem;
import androidx.media3.common.MimeTypes;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.datasource.DefaultHttpDataSource;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.hls.HlsMediaSource;
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
    private Button btnSubSelector, btnSubStyle;
    private ImageButton btnPlayerBack;
    private View layoutTopBar;
    private View layoutBuffering;
    private TextView tvBufferingText;
    private TextView tvSubtitles;
    private final Handler handler = new Handler(Looper.getMainLooper());

    private String slug;
    private int ep;
    private String title;
    private float currentBrightness = 0.5f;
    private float currentVolumeFraction = -1f;

    // Subtitle Engine State
    public static class SubtitleCue {
        public final long startMs;
        public final long endMs;
        public final String text;

        public SubtitleCue(long startMs, long endMs, String text) {
            this.startMs = startMs;
            this.endMs = endMs;
            this.text = text;
        }
    }

    private volatile List<SubtitleCue> currentCues = new ArrayList<>();
    private int currentSubLoadId = 0;

    private String rawStreamUrl = "";
    private String streamReferer = "";
    private List<JSONObject> subtitleTracks = new ArrayList<>();
    private String enSourceSubUrl = "";
    private String idNativeSubUrl = "";
    private String activeSubUrl = "";
    private String activeSubLang = "id"; // Default Indonesian
    private String activeEngine = "aigtx"; // "aigtx" | "gtx" | "ai" | "raw"
    private boolean subEnabled = true;
    private boolean hasAiKey = false;
    private String configuredAiModel = "gemini-3.1-flash-lite";

    private final Runnable subtitleSyncRunnable = new Runnable() {
        @Override
        public void run() {
            if (player != null && subEnabled) {
                long pos = player.getCurrentPosition();
                SubtitleCue active = findActiveCue(pos);
                if (active != null) {
                    if (tvSubtitles.getVisibility() != View.VISIBLE || !active.text.equals(tvSubtitles.getText().toString())) {
                        tvSubtitles.setText(active.text);
                        tvSubtitles.setVisibility(View.VISIBLE);
                    }
                } else {
                    if (tvSubtitles.getVisibility() == View.VISIBLE) {
                        tvSubtitles.setText("");
                        tvSubtitles.setVisibility(View.GONE);
                    }
                }
            } else {
                if (tvSubtitles != null && tvSubtitles.getVisibility() == View.VISIBLE) {
                    tvSubtitles.setText("");
                    tvSubtitles.setVisibility(View.GONE);
                }
            }

            if (player != null && player.isPlaying()) {
                handler.postDelayed(this, 75);
            }
        }
    };

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

        layoutBuffering = findViewById(R.id.layout_buffering);
        tvBufferingText = findViewById(R.id.tv_buffering_text);
        tvSubtitles = findViewById(R.id.tv_subtitles);

        if (title != null && !title.isEmpty()) {
            tvPlayerTitle.setText(title + " - Ep " + ep);
        } else {
            tvPlayerTitle.setText("Episode " + ep);
        }

        btnPlayerBack.setOnClickListener(v -> finish());
        btnSubSelector.setOnClickListener(v -> showSubtitleSelectorDialog());
        btnSubStyle = findViewById(R.id.btn_sub_style);
        if (btnSubStyle != null) {
            btnSubStyle.setOnClickListener(v -> showSubtitleStyleDialog());
        }

        applySubtitleStyle();

        audioManager = (AudioManager) getSystemService(Context.AUDIO_SERVICE);

        checkAiConfig();
        initExoPlayer();
        setupGestureControls();
        resolveAndPlayStream();
    }

    private void checkAiConfig() {
        new Thread(() -> {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL("http://127.0.0.1:8767/api/settings").openConnection();
                conn.setConnectTimeout(2500);
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
                hasAiKey = !k.isEmpty();
                if (!m.isEmpty()) configuredAiModel = m;
            } catch (Exception ignored) {}
        }).start();
    }

    private void initExoPlayer() {
        player = new ExoPlayer.Builder(this).build();
        playerView.setPlayer(player);

        // Hide default ExoPlayer subtitle view since we use seamless custom overlay
        SubtitleView subView = playerView.getSubtitleView();
        if (subView != null) {
            subView.setVisibility(View.GONE);
        }

        player.addListener(new Player.Listener() {
            @Override
            public void onPlaybackStateChanged(int playbackState) {
                if (playbackState == Player.STATE_BUFFERING) {
                    if (layoutBuffering != null) {
                        layoutBuffering.setVisibility(View.VISIBLE);
                        if (tvBufferingText != null) tvBufferingText.setText("MEMUAT STREAM...");
                    }
                } else if (playbackState == Player.STATE_READY) {
                    if (layoutBuffering != null) {
                        layoutBuffering.setVisibility(View.GONE);
                    }
                } else if (playbackState == Player.STATE_ENDED) {
                    if (layoutBuffering != null) {
                        layoutBuffering.setVisibility(View.GONE);
                    }
                }
            }

            @Override
            public void onIsPlayingChanged(boolean isPlaying) {
                if (isPlaying) {
                    handler.removeCallbacks(subtitleSyncRunnable);
                    handler.post(subtitleSyncRunnable);
                }
            }

            @Override
            public void onPositionDiscontinuity(Player.PositionInfo oldPosition, Player.PositionInfo newPosition, int reason) {
                handler.post(subtitleSyncRunnable);
            }

            @Override
            public void onPlayerError(PlaybackException error) {
                if (layoutBuffering != null) {
                    layoutBuffering.setVisibility(View.GONE);
                }
                Toast.makeText(PlayerActivity.this, "Player error: " + error.getMessage(), Toast.LENGTH_LONG).show();
            }
        });
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
            if (event.getAction() == MotionEvent.ACTION_DOWN) {
                if (audioManager != null) {
                    int maxVol = audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC);
                    int curVol = audioManager.getStreamVolume(AudioManager.STREAM_MUSIC);
                    currentVolumeFraction = maxVol > 0 ? ((float) curVol / (float) maxVol) : 0f;
                }
            } else if (event.getAction() == MotionEvent.ACTION_UP || event.getAction() == MotionEvent.ACTION_CANCEL) {
                currentVolumeFraction = -1f;
            }
            gestureDetector.onTouchEvent(event);
            return false;
        });
    }

    private void seekRelative(long deltaMs) {
        if (player != null) {
            long newPos = Math.max(0, Math.min(player.getDuration(), player.getCurrentPosition() + deltaMs));
            player.seekTo(newPos);
            handler.post(subtitleSyncRunnable);
        }
    }

    private void adjustVolume(float percent) {
        if (audioManager == null) return;
        int maxVol = audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC);
        if (maxVol <= 0) return;

        if (currentVolumeFraction < 0) {
            int curVol = audioManager.getStreamVolume(AudioManager.STREAM_MUSIC);
            currentVolumeFraction = (float) curVol / (float) maxVol;
        }

        // Akumulator float kontinu (sama seperti brightness) agar gerakan lambat tidak terpotong menjadi 0
        currentVolumeFraction = Math.max(0.0f, Math.min(1.0f, currentVolumeFraction + (percent * 1.2f)));
        int targetVol = Math.round(currentVolumeFraction * maxVol);
        int curVol = audioManager.getStreamVolume(AudioManager.STREAM_MUSIC);
        if (targetVol != curVol) {
            audioManager.setStreamVolume(AudioManager.STREAM_MUSIC, targetVol, 0);
        }

        int pct = Math.round(currentVolumeFraction * 100);
        showOsd(targetVol == 0 ? "🔇" : "🔊", pct);
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
        runOnUiThread(() -> {
            if (layoutBuffering != null) {
                layoutBuffering.setVisibility(View.VISIBLE);
                if (tvBufferingText != null) tvBufferingText.setText("MENYIAPKAN STREAM...");
            }
        });

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
                    String foundEnSub = "";
                    String foundIdSub = "";
                    String foundDefSub = "";
                    String foundNonArSub = "";

                    if (subArr != null) {
                        for (int i = 0; i < subArr.length(); i++) {
                            JSONObject s = subArr.getJSONObject(i);
                            subtitleTracks.add(s);
                            String lang = s.optString("lang", "").toLowerCase();
                            String lbl = s.optString("label", "").toLowerCase();
                            String url = s.optString("url", "");
                            boolean isDef = s.optBoolean("default", false);

                            boolean isArabic = lang.equals("ar") || lang.equals("ara") || lbl.contains("arabic") || lbl.contains("arab");
                            boolean isEnglish = lang.equals("en") || lang.equals("eng") || lbl.contains("english") || lbl.startsWith("eng");
                            boolean isIndo = lang.equals("id") || lang.equals("ind") || lbl.contains("indonesia") || lbl.contains("bahasa");

                            if (foundEnSub.isEmpty() && isEnglish && !url.isEmpty()) {
                                foundEnSub = url;
                            }
                            if (foundIdSub.isEmpty() && isIndo && !url.isEmpty()) {
                                foundIdSub = url;
                            }
                            if (foundDefSub.isEmpty() && isDef && !isArabic && !url.isEmpty()) {
                                foundDefSub = url;
                            }
                            if (foundNonArSub.isEmpty() && !isArabic && !url.isEmpty()) {
                                foundNonArSub = url;
                            }
                        }
                    }

                    // Backend juga menyediakan resolved default sub di data.optString("sub")
                    String backendSub = data.optString("sub", "");
                    String backendSubLang = data.optString("sub_lang", "").toLowerCase();
                    boolean backendIsArabic = backendSubLang.contains("arab") || backendSubLang.equals("ar");

                    if (foundEnSub.isEmpty()) {
                        if (!backendSub.isEmpty() && !backendIsArabic) {
                            foundEnSub = backendSub;
                        } else if (!foundDefSub.isEmpty()) {
                            foundEnSub = foundDefSub;
                        } else if (!foundNonArSub.isEmpty()) {
                            foundEnSub = foundNonArSub;
                        } else if (!subtitleTracks.isEmpty()) {
                            foundEnSub = subtitleTracks.get(0).optString("url", "");
                        }
                    }

                    enSourceSubUrl = foundEnSub;
                    idNativeSubUrl = foundIdSub;

                    // Tentukan activeSubUrl berdasarkan preferensi engine saat ini
                    if ("id".equals(activeSubLang) && "raw".equals(activeEngine) && !idNativeSubUrl.isEmpty()) {
                        activeSubUrl = idNativeSubUrl;
                    } else if ("en".equals(activeSubLang) && "raw".equals(activeEngine)) {
                        activeSubUrl = enSourceSubUrl;
                    } else {
                        // Terjemahan (AIGTX, AI, GTX) menggunakan enSourceSubUrl sebagai sumber terjemahan
                        activeSubUrl = !enSourceSubUrl.isEmpty() ? enSourceSubUrl : (foundNonArSub.isEmpty() ? foundEnSub : foundNonArSub);
                    }

                    rawStreamUrl = streamUrl;
                    streamReferer = referer;

                    if (!rawStreamUrl.isEmpty()) {
                        runOnUiThread(this::applyCurrentStream);
                    }
                } else {
                    runOnUiThread(() -> {
                        if (layoutBuffering != null) layoutBuffering.setVisibility(View.GONE);
                        Toast.makeText(this, "Gagal resolve: " + res.optString("error"), Toast.LENGTH_LONG).show();
                    });
                }
            } catch (Exception e) {
                runOnUiThread(() -> {
                    if (layoutBuffering != null) layoutBuffering.setVisibility(View.GONE);
                    Toast.makeText(this, "Error streaming: " + e.getMessage(), Toast.LENGTH_SHORT).show();
                });
            }
        }).start();
    }

    private void applyCurrentStream() {
        if (rawStreamUrl.isEmpty()) return;

        if (layoutBuffering != null) {
            layoutBuffering.setVisibility(View.VISIBLE);
            if (tvBufferingText != null) tvBufferingText.setText("MEMUAT STREAM...");
        }

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

        // Pure video playback - completely decoupled from subtitles to avoid player reloads/black screen
        player.setMediaSource(videoSource);
        player.prepare();
        player.play();

        applySubtitleSelection();
    }

    private void applySubtitleSelection() {
        updateSubStatusText(false);

        if (!subEnabled || activeSubUrl == null || activeSubUrl.isEmpty()) {
            currentCues = new ArrayList<>();
            runOnUiThread(() -> {
                if (tvSubtitles != null) {
                    tvSubtitles.setText("");
                    tvSubtitles.setVisibility(View.GONE);
                }
            });
            return;
        }

        try {
            String subModeParam = activeEngine.equals("raw") ? "" : activeEngine;
            String srcParam = activeEngine.equals("raw") ? activeSubLang : "en";

            String encodedSubUrl = URLEncoder.encode(activeSubUrl, "UTF-8");
            String encodedRef = URLEncoder.encode(streamReferer != null ? streamReferer : "", "UTF-8");

            // Jika memilih terjemahan (AIGTX / AI / GTX) dan cues belum dimuat:
            // Unduh dulu subtitle sumber (English/Native) secara instan (0.5s) agar penonton tidak mengalami black screen / tanpa sub.
            if (!subModeParam.isEmpty() && currentCues.isEmpty() && enSourceSubUrl != null && !enSourceSubUrl.isEmpty()) {
                String rawSubUrl = "http://127.0.0.1:8767/api/player/sub?url=" + URLEncoder.encode(enSourceSubUrl, "UTF-8")
                        + "&referer=" + encodedRef
                        + "&src=" + URLEncoder.encode(srcParam, "UTF-8")
                        + "&lang=" + URLEncoder.encode(srcParam, "UTF-8");
                loadSubtitlesAsync(rawSubUrl, true);
            }

            // Bangun URL utama untuk terjemahan atau subtitle yang dipilih
            String proxiedSub = "http://127.0.0.1:8767/api/player/sub?url=" + encodedSubUrl
                    + "&referer=" + encodedRef
                    + "&src=" + URLEncoder.encode(srcParam, "UTF-8")
                    + "&lang=" + URLEncoder.encode(activeSubLang, "UTF-8")
                    + (subModeParam.isEmpty() ? "" : "&mode=" + URLEncoder.encode(subModeParam, "UTF-8"));

            loadSubtitlesAsync(proxiedSub, false);
        } catch (Exception e) {
            updateSubStatusText(false);
            if (tvSubStatus != null) {
                tvSubStatus.setText("Sub: Gagal (" + e.getMessage() + ")");
            }
        }
    }

    private void loadSubtitlesAsync(String subUrl, boolean isImmediateFallback) {
        final int loadId = ++currentSubLoadId;
        new Thread(() -> {
            HttpURLConnection conn = null;
            try {
                conn = (HttpURLConnection) new URL(subUrl).openConnection();
                conn.setConnectTimeout(15000);
                // Beri waktu cukup (80 detik) bila translasi baru pertama kali dijalankan
                conn.setReadTimeout(isImmediateFallback ? 12000 : 80000);
                conn.setRequestProperty("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0");
                conn.setInstanceFollowRedirects(true);

                int respCode = conn.getResponseCode();
                if (respCode >= 400) {
                    throw new Exception("HTTP " + respCode);
                }

                BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) {
                    sb.append(line).append("\n");
                }
                reader.close();

                if (loadId != currentSubLoadId && !isImmediateFallback) return; // Stale request

                List<SubtitleCue> cues = parseVtt(sb.toString());
                if (!cues.isEmpty()) {
                    currentCues = cues;
                    runOnUiThread(() -> {
                        if (!isImmediateFallback) {
                            updateSubStatusText(true);
                        }
                        subtitleSyncRunnable.run();
                    });
                }
            } catch (Exception e) {
                if (!isImmediateFallback && loadId == currentSubLoadId) {
                    runOnUiThread(() -> {
                        // Jika sudah ada cues (misal dari immediate source), jangan kosongkan layar!
                        if (!currentCues.isEmpty()) {
                            tvSubStatus.setText("Sub: " + activeSubLang.toUpperCase() + " [Menggunakan teks asli]");
                        } else {
                            updateSubStatusText(false);
                            if (tvSubStatus != null) {
                                tvSubStatus.setText("Sub: Gagal (" + e.getMessage() + ")");
                            }
                        }
                    });
                }
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
        }).start();
    }

    private void updateSubStatusText(boolean isLoaded) {
        if (tvSubStatus == null) return;
        if (!subEnabled) {
            tvSubStatus.setText("Subtitle: Nonaktif");
            return;
        }
        String engineLabel = "AIGTX (Cepat)";
        if ("gtx".equals(activeEngine)) engineLabel = "Google GTX";
        else if ("ai".equals(activeEngine)) engineLabel = "AI Fansub (" + configuredAiModel + ")";
        else if ("raw".equals(activeEngine)) {
            if ("en".equals(activeSubLang)) engineLabel = "Source English";
            else if ("id".equals(activeSubLang)) engineLabel = "Asli / Resmi";
            else engineLabel = "Source Asli";
        }

        String suffix = isLoaded ? "" : " [Memuat...]";
        tvSubStatus.setText("Sub: " + activeSubLang.toUpperCase() + " • " + engineLabel + suffix);
    }

    private static long parseTimestamp(String token) {
        if (token == null) return -1;
        token = token.trim();
        // Hapus WebVTT settings di baris waktu (misal align:start position:0%)
        int spaceIdx = -1;
        for (int i = 0; i < token.length(); i++) {
            char c = token.charAt(i);
            if (c == ' ' || c == '\t') {
                spaceIdx = i;
                break;
            }
        }
        if (spaceIdx != -1) {
            token = token.substring(0, spaceIdx).trim();
        }
        token = token.replace(',', '.');
        String[] parts = token.split(":");
        try {
            if (parts.length == 3) {
                long h = Long.parseLong(parts[0].trim());
                long m = Long.parseLong(parts[1].trim());
                double s = Double.parseDouble(parts[2].trim());
                return (long) ((h * 3600 + m * 60 + s) * 1000);
            } else if (parts.length == 2) {
                long m = Long.parseLong(parts[0].trim());
                double s = Double.parseDouble(parts[1].trim());
                return (long) ((m * 60 + s) * 1000);
            }
        } catch (Exception ignored) {}
        return -1;
    }

    private List<SubtitleCue> parseVtt(String content) {
        List<SubtitleCue> list = new ArrayList<>();
        if (content == null || content.isEmpty()) return list;

        // Buang BOM jika ada
        if (content.startsWith("\uFEFF")) {
            content = content.substring(1);
        }

        String[] lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n");
        long curStart = -1;
        long curEnd = -1;
        StringBuilder curText = new StringBuilder();

        for (String rawLine : lines) {
            String line = rawLine.trim();

            if (line.contains("-->")) {
                // Simpan cue sebelumnya jika belum sempat ter-flush
                if (curStart != -1 && curEnd != -1 && curText.length() > 0) {
                    String cleaned = curText.toString().replaceAll("<[^>]*>", "").trim();
                    if (!cleaned.isEmpty()) {
                        list.add(new SubtitleCue(curStart, curEnd, cleaned));
                    }
                    curText.setLength(0);
                }

                String[] timeParts = line.split("-->");
                if (timeParts.length >= 2) {
                    curStart = parseTimestamp(timeParts[0]);
                    curEnd = parseTimestamp(timeParts[1]);
                }
            } else if (line.isEmpty()) {
                if (curStart != -1 && curEnd != -1 && curText.length() > 0) {
                    String cleaned = curText.toString().replaceAll("<[^>]*>", "").trim();
                    if (!cleaned.isEmpty()) {
                        list.add(new SubtitleCue(curStart, curEnd, cleaned));
                    }
                }
                curStart = -1;
                curEnd = -1;
                curText.setLength(0);
            } else if (curStart != -1 && curEnd != -1) {
                // Abaikan header atau komentar WebVTT
                if (!line.startsWith("NOTE") && !line.startsWith("STYLE") && !line.startsWith("REGION")) {
                    if (curText.length() > 0) curText.append("\n");
                    curText.append(line);
                }
            }
        }

        if (curStart != -1 && curEnd != -1 && curText.length() > 0) {
            String cleaned = curText.toString().replaceAll("<[^>]*>", "").trim();
            if (!cleaned.isEmpty()) {
                list.add(new SubtitleCue(curStart, curEnd, cleaned));
            }
        }
        return list;
    }

    private SubtitleCue findActiveCue(long posMs) {
        List<SubtitleCue> cues = currentCues;
        if (cues == null || cues.isEmpty()) return null;
        int low = 0;
        int high = cues.size() - 1;
        int best = -1;
        while (low <= high) {
            int mid = (low + high) >>> 1;
            SubtitleCue cue = cues.get(mid);
            if (cue.startMs <= posMs) {
                best = mid;
                low = mid + 1;
            } else {
                high = mid - 1;
            }
        }
        if (best != -1) {
            SubtitleCue c = cues.get(best);
            if (posMs <= c.endMs) return c;
        }
        return null;
    }

    private void showSubtitleSelectorDialog() {
        AlertDialog.Builder builder = new AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert);
        builder.setTitle("Pengaturan Subtitle & Mesin Terjemahan");

        List<String> options = new ArrayList<>();
        List<Runnable> actions = new ArrayList<>();

        // 1. AIGTX (Default & Direkomendasikan)
        boolean isAigtxSelected = subEnabled && "id".equals(activeSubLang) && "aigtx".equals(activeEngine);
        options.add("🇮🇩 Bahasa Indonesia (AIGTX - Instan & Cerdas)" + (isAigtxSelected ? " ✓" : ""));
        actions.add(() -> {
            subEnabled = true;
            activeSubLang = "id";
            activeEngine = "aigtx";
            activeSubUrl = enSourceSubUrl;
        });

        // 2. AI Fansub
        boolean isAiSelected = subEnabled && "id".equals(activeSubLang) && "ai".equals(activeEngine);
        String aiOptionText = "🇮🇩 Bahasa Indonesia (AI Fansub / " + configuredAiModel + ")"
                + (hasAiKey ? " [SIAP]" : " [Butuh Key]")
                + (isAiSelected ? " ✓" : "");
        options.add(aiOptionText);
        actions.add(() -> {
            subEnabled = true;
            activeSubLang = "id";
            activeEngine = "ai";
            activeSubUrl = enSourceSubUrl;
            if (!hasAiKey) {
                Toast.makeText(this, "Perhatian: API Key AI belum disetel (:apikey <key> di home). Menggunakan AIGTX sebagai fallback otomatis.", Toast.LENGTH_LONG).show();
            }
        });

        // 3. Google GTX Murni
        boolean isGtxSelected = subEnabled && "id".equals(activeSubLang) && "gtx".equals(activeEngine);
        options.add("🇮🇩 Bahasa Indonesia (Google GTX Murni)" + (isGtxSelected ? " ✓" : ""));
        actions.add(() -> {
            subEnabled = true;
            activeSubLang = "id";
            activeEngine = "gtx";
            activeSubUrl = enSourceSubUrl;
        });

        // 4. Native Indonesian (jika tersedia di track asli)
        if (!idNativeSubUrl.isEmpty()) {
            boolean isIdNativeSelected = subEnabled && "id".equals(activeSubLang) && "raw".equals(activeEngine) && idNativeSubUrl.equals(activeSubUrl);
            options.add("🇮🇩 Bahasa Indonesia (Asli / Bawaan)" + (isIdNativeSelected ? " ✓" : ""));
            actions.add(() -> {
                subEnabled = true;
                activeSubLang = "id";
                activeEngine = "raw";
                activeSubUrl = idNativeSubUrl;
            });
        }

        // 5. English (Original)
        if (!enSourceSubUrl.isEmpty()) {
            boolean isEnSelected = subEnabled && "en".equals(activeSubLang) && "raw".equals(activeEngine);
            options.add("🇬🇧 English (Original / Asli)" + (isEnSelected ? " ✓" : ""));
            actions.add(() -> {
                subEnabled = true;
                activeSubLang = "en";
                activeEngine = "raw";
                activeSubUrl = enSourceSubUrl;
            });
        }

        // 6. Daftar track bahasa lain yang tersedia (misal Spanish, French, Japanese, dsb.)
        for (int i = 0; i < subtitleTracks.size(); i++) {
            JSONObject s = subtitleTracks.get(i);
            String url = s.optString("url", "");
            String lbl = s.optString("label", "Track " + (i + 1));
            String lang = s.optString("lang", "").toLowerCase();
            // Lewati track English & ID native karena sudah disediakan di menu utama di atas
            if (url.equals(enSourceSubUrl) || url.equals(idNativeSubUrl)) {
                continue;
            }
            boolean isThisSelected = subEnabled && "raw".equals(activeEngine) && url.equals(activeSubUrl);
            options.add("🌐 " + lbl + (isThisSelected ? " ✓" : ""));
            actions.add(() -> {
                subEnabled = true;
                activeSubLang = lang.isEmpty() ? "en" : lang;
                activeEngine = "raw";
                activeSubUrl = url;
            });
        }

        // 7. Pengaturan Tampilan & Gaya Subtitle
        options.add("⚙️ Pengaturan Tampilan (Posisi, Latar Belakang & Ukuran)...");
        actions.add(this::showSubtitleStyleDialog);

        // 8. Matikan Subtitle
        options.add("❌ Matikan Subtitle" + (!subEnabled ? " ✓" : ""));
        actions.add(() -> {
            subEnabled = false;
        });

        builder.setItems(options.toArray(new String[0]), (dialog, which) -> {
            if (which >= 0 && which < actions.size()) {
                actions.get(which).run();
                applySubtitleSelection();
                Toast.makeText(this, "Subtitle diperbarui: " + (subEnabled ? activeSubLang.toUpperCase() + " [" + activeEngine + "]" : "OFF"), Toast.LENGTH_SHORT).show();
            }
        });

        builder.setNegativeButton("Tutup", (dialog, which) -> dialog.dismiss());
        builder.show();
    }

    private void applySubtitleStyle() {
        if (tvSubtitles == null) return;
        SharedPreferences sp = getSharedPreferences("tatap_player_prefs", Context.MODE_PRIVATE);
        String pos = sp.getString("sub_pos", "low");
        String bg = sp.getString("sub_bg", "subtle");
        String size = sp.getString("sub_size", "medium");

        // 1. Margin Bawah (Posisi - mengatasi komplain posisi terlalu tinggi)
        int marginDp = 22; // Default 22dp: Rendah & pas di batas bawah layar
        if ("mid".equals(pos)) marginDp = 36;
        else if ("high".equals(pos)) marginDp = 54;

        int marginPx = (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, marginDp, getResources().getDisplayMetrics());
        ViewGroup.MarginLayoutParams lp = (ViewGroup.MarginLayoutParams) tvSubtitles.getLayoutParams();
        if (lp != null) {
            lp.bottomMargin = marginPx;
            tvSubtitles.setLayoutParams(lp);
        }

        // 2. Ukuran Font
        float sizeSp = 17f;
        if ("small".equals(size)) sizeSp = 14f;
        else if ("large".equals(size)) sizeSp = 21f;
        tvSubtitles.setTextSize(TypedValue.COMPLEX_UNIT_SP, sizeSp);

        // 3. Latar Belakang & Shadow (mengatasi komplain background terlalu pekat)
        GradientDrawable gd = new GradientDrawable();
        int cornerPx = (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, 6, getResources().getDisplayMetrics());
        gd.setCornerRadius(cornerPx);

        if ("transparent".equals(bg)) {
            // Tanpa box background sama sekali, teks tebal dengan shadow tajam (gaya fansub modern)
            tvSubtitles.setBackground(null);
            tvSubtitles.setShadowLayer(6f, 2f, 2f, 0xFF000000);
        } else {
            int bgColor = 0x4D000000; // 30% alpha (samar & lembut, tidak pekat)
            if ("medium".equals(bg)) bgColor = 0x8C000000; // 55%
            else if ("dark".equals(bg)) bgColor = 0xCC000000; // 80% pekat
            gd.setColor(bgColor);
            tvSubtitles.setBackground(gd);
            tvSubtitles.setShadowLayer(4f, 1.5f, 1.5f, 0xFF000000);
        }
    }

    private void showSubtitleStyleDialog() {
        AlertDialog.Builder builder = new AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert);
        builder.setTitle("Pengaturan Tampilan Subtitle");

        SharedPreferences sp = getSharedPreferences("tatap_player_prefs", Context.MODE_PRIVATE);
        String curPos = sp.getString("sub_pos", "low");
        String curBg = sp.getString("sub_bg", "subtle");
        String curSize = sp.getString("sub_size", "medium");

        String posLabel = "low".equals(curPos) ? "Bawah (22dp) [Pas]" : ("mid".equals(curPos) ? "Sedang (36dp)" : "Tinggi (54dp)");
        String bgLabel = "transparent".equals(curBg) ? "Transparan (Tanpa Box)" : ("subtle".equals(curBg) ? "Samar / Lembut (30%)" : ("medium".equals(curBg) ? "Sedang (55%)" : "Pekat (80%)"));
        String sizeLabel = "small".equals(curSize) ? "Kecil (14sp)" : ("large".equals(curSize) ? "Besar (21sp)" : "Sedang (17sp)");

        String[] menu = new String[]{
                "📍 Posisi Subtitle: " + posLabel,
                "🎨 Latar Belakang: " + bgLabel,
                "🔤 Ukuran Huruf: " + sizeLabel,
                "🔄 Reset ke Default"
        };

        builder.setItems(menu, (dialog, which) -> {
            if (which == 0) {
                showPositionPicker(sp);
            } else if (which == 1) {
                showBackgroundPicker(sp);
            } else if (which == 2) {
                showSizePicker(sp);
            } else if (which == 3) {
                sp.edit().putString("sub_pos", "low").putString("sub_bg", "subtle").putString("sub_size", "medium").apply();
                applySubtitleStyle();
                Toast.makeText(this, "Tampilan subtitle direset ke default", Toast.LENGTH_SHORT).show();
            }
        });

        builder.setNegativeButton("Tutup", (dialog, which) -> dialog.dismiss());
        builder.show();
    }

    private void showPositionPicker(SharedPreferences sp) {
        String[] options = new String[]{
                "Bawah / Rendah (22dp) [Direkomendasikan]",
                "Sedang (36dp)",
                "Tinggi (54dp)"
        };
        String cur = sp.getString("sub_pos", "low");
        int checked = "high".equals(cur) ? 2 : ("mid".equals(cur) ? 1 : 0);

        new AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
                .setTitle("Pilih Posisi Subtitle")
                .setSingleChoiceItems(options, checked, (dialog, which) -> {
                    String val = which == 2 ? "high" : (which == 1 ? "mid" : "low");
                    sp.edit().putString("sub_pos", val).apply();
                    applySubtitleStyle();
                    dialog.dismiss();
                    Toast.makeText(this, "Posisi subtitle disimpan", Toast.LENGTH_SHORT).show();
                })
                .setNegativeButton("Batal", null)
                .show();
    }

    private void showBackgroundPicker(SharedPreferences sp) {
        String[] options = new String[]{
                "Transparan (Tanpa Box / Shadow Teks Bersih)",
                "Samar / Lembut (30% Alpha) [Direkomendasikan]",
                "Sedang (55% Alpha)",
                "Pekat (80% Alpha)"
        };
        String cur = sp.getString("sub_bg", "subtle");
        int checked = "transparent".equals(cur) ? 0 : ("medium".equals(cur) ? 2 : ("dark".equals(cur) ? 3 : 1));

        new AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
                .setTitle("Pilih Latar Belakang Subtitle")
                .setSingleChoiceItems(options, checked, (dialog, which) -> {
                    String val = which == 0 ? "transparent" : (which == 2 ? "medium" : (which == 3 ? "dark" : "subtle"));
                    sp.edit().putString("sub_bg", val).apply();
                    applySubtitleStyle();
                    dialog.dismiss();
                    Toast.makeText(this, "Gaya latar subtitle disimpan", Toast.LENGTH_SHORT).show();
                })
                .setNegativeButton("Batal", null)
                .show();
    }

    private void showSizePicker(SharedPreferences sp) {
        String[] options = new String[]{
                "Kecil (14sp)",
                "Sedang (17sp) [Direkomendasikan]",
                "Besar (21sp)"
        };
        String cur = sp.getString("sub_size", "medium");
        int checked = "small".equals(cur) ? 0 : ("large".equals(cur) ? 2 : 1);

        new AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
                .setTitle("Pilih Ukuran Huruf Subtitle")
                .setSingleChoiceItems(options, checked, (dialog, which) -> {
                    String val = which == 0 ? "small" : (which == 2 ? "large" : "medium");
                    sp.edit().putString("sub_size", val).apply();
                    applySubtitleStyle();
                    dialog.dismiss();
                    Toast.makeText(this, "Ukuran subtitle disimpan", Toast.LENGTH_SHORT).show();
                })
                .setNegativeButton("Batal", null)
                .show();
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (player != null) player.pause();
        handler.removeCallbacks(subtitleSyncRunnable);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (player != null && player.isPlaying()) {
            handler.removeCallbacks(subtitleSyncRunnable);
            handler.post(subtitleSyncRunnable);
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        handler.removeCallbacks(subtitleSyncRunnable);
        if (player != null) {
            player.release();
            player = null;
        }
    }
}
