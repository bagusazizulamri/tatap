package id.tatap.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Context;
import android.content.pm.ActivityInfo;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;

public class MainActivity extends Activity {
    private WebView webView;
    private FrameLayout customViewContainer;
    private WebChromeClient.CustomViewCallback customViewCallback;
    private View customView;

    public class TatapNativeBridge {
        private final Activity activity;

        public TatapNativeBridge(Activity act) {
            this.activity = act;
        }

        @JavascriptInterface
        public void vibrate(long ms) {
            Vibrator v = (Vibrator) activity.getSystemService(Context.VIBRATOR_SERVICE);
            if (v != null && v.hasVibrator()) {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    v.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE));
                } else {
                    v.vibrate(ms);
                }
            }
        }

        @JavascriptInterface
        public void setBrightness(final float brightnessRatio) {
            activity.runOnUiThread(() -> {
                Window win = activity.getWindow();
                WindowManager.LayoutParams lp = win.getAttributes();
                lp.screenBrightness = Math.max(0.01f, Math.min(1.0f, brightnessRatio));
                win.setAttributes(lp);
            });
        }

        @JavascriptInterface
        public void setOrientation(final String mode) {
            activity.runOnUiThread(() -> {
                if ("landscape".equalsIgnoreCase(mode)) {
                    activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);
                } else if ("portrait".equalsIgnoreCase(mode)) {
                    activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT);
                } else {
                    activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED);
                }
            });
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Keep screen on while playing
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        // Immersive full-screen status/nav bars
        Window window = getWindow();
        window.setStatusBarColor(Color.parseColor("#08090c"));
        window.setNavigationBarColor(Color.parseColor("#08090c"));

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.parseColor("#08090c"));

        webView = new WebView(this);
        customViewContainer = new FrameLayout(this);
        customViewContainer.setVisibility(View.GONE);
        customViewContainer.setBackgroundColor(Color.BLACK);

        root.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        root.addView(customViewContainer, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        setContentView(root);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        settings.setUserAgentString(settings.getUserAgentString() + " TatapAndroid/2.2.0");

        webView.addJavascriptInterface(new TatapNativeBridge(this), "TatapNative");

        webView.setWebViewClient(new WebViewClient());
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onShowCustomView(View view, CustomViewCallback callback) {
                if (customView != null) {
                    callback.onCustomViewHidden();
                    return;
                }
                customView = view;
                customViewCallback = callback;
                webView.setVisibility(View.GONE);
                customViewContainer.setVisibility(View.VISIBLE);
                customViewContainer.addView(view);
                setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);
            }

            @Override
            public void onHideCustomView() {
                if (customView == null) return;
                webView.setVisibility(View.VISIBLE);
                customViewContainer.setVisibility(View.GONE);
                customViewContainer.removeView(customView);
                if (customViewCallback != null) {
                    customViewCallback.onCustomViewHidden();
                }
                customView = null;
                setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED);
            }
        });

        // Start embedded Python backend via Chaquopy if available
        startEmbeddedBackend();

        // Load local backend or configured Tatap instance
        android.content.SharedPreferences prefs = getSharedPreferences("tatap_prefs", Context.MODE_PRIVATE);
        String serverUrl = getIntent().getStringExtra("server_url");
        if (serverUrl == null || serverUrl.isEmpty()) {
            serverUrl = prefs.getString("server_url", "http://127.0.0.1:8767");
        } else {
            prefs.edit().putString("server_url", serverUrl).apply();
        }

        final String targetServer = serverUrl;
        
        // Polling loop sampai server 127.0.0.1:8767 siap
        waitForServerAndLoad(targetServer, 0);
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
                // Chaquopy not bundled or failed, fallback to external or asset mode
                t.printStackTrace();
            }
        }).start();
    }

    private void waitForServerAndLoad(final String targetServer, final int attempt) {
        new Thread(() -> {
            boolean ready = false;
            try {
                java.net.HttpURLConnection conn = (java.net.HttpURLConnection) new java.net.URL(targetServer + "/api/ping").openConnection();
                conn.setConnectTimeout(600);
                conn.setReadTimeout(600);
                ready = (conn.getResponseCode() == 200);
                conn.disconnect();
            } catch (Exception ignored) {}

            if (ready || attempt >= 15) {
                runOnUiThread(() -> {
                    if (ready) {
                        webView.loadUrl(targetServer);
                    } else {
                        // Fallback ke local asset
                        webView.loadUrl("file:///android_asset/frontend/index.html");
                    }
                });
            } else {
                try { Thread.sleep(400); } catch (Exception ignored) {}
                waitForServerAndLoad(targetServer, attempt + 1);
            }
        }).start();
    }

    @Override
    public void onBackPressed() {
        if (customView != null) {
            webView.getWebChromeClient().onHideCustomView();
        } else if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
