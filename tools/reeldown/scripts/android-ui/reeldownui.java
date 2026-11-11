import com.android.uiautomator.core.UiDevice;
import com.android.uiautomator.core.UiObject;
import com.android.uiautomator.core.UiSelector;
import com.android.uiautomator.testrunner.UiAutomatorTestCase;
import android.view.accessibility.AccessibilityNodeInfo;
import java.lang.reflect.Method;
import java.util.List;
import java.util.ArrayList;
import java.util.ArrayDeque;
import android.graphics.Rect;
import org.json.JSONArray;
import org.json.JSONObject;

public class reeldownui extends UiAutomatorTestCase {
    private boolean onScreen(AccessibilityNodeInfo node, UiDevice device) {
        Rect rect = new Rect(); node.getBoundsInScreen(rect);
        return node.isVisibleToUser() && Rect.intersects(rect, new Rect(0, 0, device.getDisplayWidth(), device.getDisplayHeight()));
    }
    public void testAction() throws Exception {
        String pkg = getParams().getString("pkg");
        if (!"com.phoenix.read".equals(pkg) &&
            !"com.ss.android.ugc.aweme".equals(pkg) &&
            !"com.emanuelef.remote_capture".equals(pkg)) {
            throw new IllegalArgumentException("Unsupported task app");
        }
        UiDevice device = getUiDevice();
        if (!pkg.equals(device.getCurrentPackageName())) {
            throw new IllegalStateException("Task app is not foreground");
        }
        String mode = getParams().getString("mode");
        boolean clicked;
        if (mode != null && (mode.startsWith("semantic_") || "snapshot".equals(mode))) {
            Method method = UiDevice.class.getDeclaredMethod("getAutomatorBridge");
            method.setAccessible(true);
            Object bridge = method.invoke(device);
            Method rootMethod = bridge.getClass().getMethod("getRootInActiveWindow");
            rootMethod.setAccessible(true);
            AccessibilityNodeInfo root = (AccessibilityNodeInfo) rootMethod.invoke(bridge);
            if (root == null || !pkg.contentEquals(root.getPackageName())) {
                throw new IllegalStateException("Task window unavailable");
            }
            if ("snapshot".equals(mode)) {
                JSONArray rows = new JSONArray();
                ArrayDeque<AccessibilityNodeInfo> queue = new ArrayDeque<AccessibilityNodeInfo>();
                queue.add(root);
                int visited = 0;
                while (!queue.isEmpty() && visited++ < 5000 && rows.length() < 300) {
                    AccessibilityNodeInfo node = queue.removeFirst();
                    if (pkg.contentEquals(node.getPackageName()) && onScreen(node, device) && !node.isPassword()) {
                        CharSequence label = node.getText() != null ? node.getText() : node.getContentDescription();
                        String text = label == null ? "" : label.toString();
                        if (text.matches("(?is).*(https?://|cookie\\s*[:=]|authorization\\s*[:=]).*")) text = "<private request data>";
                        if (!text.isEmpty() || node.isClickable() || node.isCheckable()) {
                            Rect rect = new Rect(); node.getBoundsInScreen(rect);
                            rows.put(new JSONObject().put("text", text.substring(0, Math.min(500, text.length())))
                                .put("id", node.getViewIdResourceName()).put("bounds", rect.toShortString())
                                .put("clickable", node.isClickable()).put("selected", node.isSelected()).put("enabled", node.isEnabled())
                                .put("checked", node.isChecked()).put("checkable", node.isCheckable()));
                        }
                    }
                    for (int i = 0; i < node.getChildCount(); i++) {
                        AccessibilityNodeInfo child = node.getChild(i);
                        if (child != null) queue.add(child);
                    }
                }
                System.out.println("REELDOWN_UI_SNAPSHOT=" + rows.toString());
                return;
            }
            List<AccessibilityNodeInfo> nodes;
            if ("semantic_id".equals(mode)) {
                nodes = root.findAccessibilityNodeInfosByViewId(getParams().getString("id"));
            } else if ("semantic_text".equals(mode)) {
                String wanted = getParams().getString("text");
                if (wanted == null && getParams().getString("text_b64") != null)
                    wanted = new String(android.util.Base64.decode(getParams().getString("text_b64"), android.util.Base64.DEFAULT), "UTF-8");
                nodes = new ArrayList<AccessibilityNodeInfo>();
                ArrayDeque<AccessibilityNodeInfo> queue = new ArrayDeque<AccessibilityNodeInfo>();
                queue.add(root);
                int visited = 0;
                while (!queue.isEmpty() && visited++ < 5000) {
                    AccessibilityNodeInfo node = queue.removeFirst();
                    if (node.getText() != null && wanted.contentEquals(node.getText()) && node.isVisibleToUser()) nodes.add(node);
                    for (int i = 0; i < node.getChildCount(); i++) {
                        AccessibilityNodeInfo child = node.getChild(i);
                        if (child != null) queue.add(child);
                    }
                }
            } else if ("semantic_point".equals(mode)) {
                int x = Integer.parseInt(getParams().getString("x"));
                int y = Integer.parseInt(getParams().getString("y"));
                ArrayDeque<AccessibilityNodeInfo> queue = new ArrayDeque<AccessibilityNodeInfo>();
                queue.add(root);
                AccessibilityNodeInfo best = null;
                long area = Long.MAX_VALUE;
                int visited = 0;
                while (!queue.isEmpty() && visited++ < 5000) {
                    AccessibilityNodeInfo node = queue.removeFirst();
                    Rect rect = new Rect(); node.getBoundsInScreen(rect);
                    long candidateArea = (long) rect.width() * rect.height();
                    if (node.isClickable() && node.isVisibleToUser() && node.isEnabled() && rect.contains(x,y) && candidateArea > 0 && candidateArea < area) {
                        best = node; area = candidateArea;
                    }
                    for (int i = 0; i < node.getChildCount(); i++) {
                        AccessibilityNodeInfo child = node.getChild(i);
                        if (child != null) queue.add(child);
                    }
                }
                nodes = new ArrayList<AccessibilityNodeInfo>();
                if (best != null) nodes.add(best);
            } else {
                throw new IllegalArgumentException("Unknown semantic mode");
            }
            List<AccessibilityNodeInfo> visible = new ArrayList<AccessibilityNodeInfo>();
            for (AccessibilityNodeInfo node : nodes) {
                if (onScreen(node, device) && node.isEnabled()) visible.add(node);
            }
            nodes = visible;
            System.out.println("REELDOWN_CONTROL_MATCHES=" + nodes.size());
            if (nodes.size() != 1 || !nodes.get(0).isEnabled() || !nodes.get(0).isVisibleToUser()) {
                throw new IllegalStateException("A unique visible control is required");
            }
            AccessibilityNodeInfo target = nodes.get(0);
            while (!target.isClickable() && target.getParent() != null) target = target.getParent();
            if (!target.isClickable() || !pkg.contentEquals(target.getPackageName())) {
                throw new IllegalStateException("No clickable task control");
            }
            clicked = target.performAction(AccessibilityNodeInfo.ACTION_CLICK);
        } else if ("id".equals(mode)) {
            UiObject obj = new UiObject(new UiSelector().packageName(pkg)
                .resourceId(getParams().getString("id")));
            if (!obj.waitForExists(3000)) throw new IllegalStateException("Control missing");
            clicked = obj.click();
        } else if ("point".equals(mode)) {
            int x = Integer.parseInt(getParams().getString("x"));
            int y = Integer.parseInt(getParams().getString("y"));
            if (x < 0 || y < 0 || x >= device.getDisplayWidth() || y >= device.getDisplayHeight()) {
                throw new IllegalArgumentException("Invalid observed point");
            }
            clicked = device.click(x, y);
        } else if ("back".equals(mode)) {
            clicked = device.pressBack();
        } else {
            throw new IllegalArgumentException("Unsupported action");
        }
        device.waitForIdle(2000);
        System.out.println("REELDOWN_UI_ACTION=" + clicked);
    }
}
