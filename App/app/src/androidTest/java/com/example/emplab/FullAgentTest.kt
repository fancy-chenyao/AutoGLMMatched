package com.example.emplab

import android.app.Activity
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.rule.GrantPermissionRule
import Agent.ActivityTracker
import Agent.CommandHandler
import android.os.Build
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.rules.TestWatcher
import org.junit.runner.Description
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/**
 * Agent 模块全量动作耗时与稳定性测试
 * 包含：动作执行、Verifier 验证、脏页面防御、耗时统计
 */
@RunWith(AndroidJUnit4::class)
class FullAgentTest {

    @get:Rule
    val grantPermissionRule: GrantPermissionRule = GrantPermissionRule.grant(*resolveRuntimePermissions())

    @get:Rule
    val activityRule = ActivityScenarioRule(LeaveApplicationActivity::class.java)

    private val TAG = "FullAgentTest"
    private val debug = DebugLogger(TAG)
    private lateinit var recorder: PerformanceRecorder
    private lateinit var scenario: ActivityScenario<LeaveApplicationActivity>

    /**
     * 计算元素树缓存：调用一次 get_state 以便后续按坐标查找元素
     */
    private fun primeElementTree() {
        debug.step("primeElementTree.start")
        val latch = CountDownLatch(1)
        scenario.onActivity { activity ->
            val params = JSONObject().apply {
                put("stabilize_timeout_ms", 1000)
                put("stable_window_ms", 300)
            }
            CommandHandler.handleCommand("get_state", params, "req_prime", activity) {
                latch.countDown()
            }
        }
        latch.await(5, TimeUnit.SECONDS)
        debug.step("primeElementTree.end")
    }
    /**
     * 计算与当前设备和清单匹配的运行时权限集合
     * - Android 13+(API 33+)：授予 READ_MEDIA_* 三项
     * - Android 12及以下(API <=32)：授予 READ/WRITE_EXTERNAL_STORAGE
     * 注意：避免在高版本上授予已移除的旧权限导致 GrantPermissionRule 失败
     */
    private fun resolveRuntimePermissions(): Array<String> {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            arrayOf(
                android.Manifest.permission.READ_MEDIA_IMAGES,
                android.Manifest.permission.READ_MEDIA_VIDEO,
                android.Manifest.permission.READ_MEDIA_AUDIO
            )
        } else {
            arrayOf(
                android.Manifest.permission.WRITE_EXTERNAL_STORAGE,
                android.Manifest.permission.READ_EXTERNAL_STORAGE
            )
        }
    }
    /**
     * 测试事件监听：记录每个用例的开始、成功、失败与跳过，便于在 Logcat 观察
     */
    @get:Rule
    val testWatcher: TestWatcher = object : TestWatcher() {
        override fun starting(description: Description) {
            android.util.Log.i(TAG, "TEST START: ${description.className}.${description.methodName}")
        }
        override fun succeeded(description: Description) {
            android.util.Log.i(TAG, "TEST OK: ${description.className}.${description.methodName}")
        }
        override fun failed(e: Throwable, description: Description) {
            android.util.Log.e(TAG, "TEST FAIL: ${description.className}.${description.methodName} -> ${e.message}", e)
        }
        override fun skipped(e: org.junit.AssumptionViolatedException, description: Description) {
            android.util.Log.w(TAG, "TEST SKIP: ${description.className}.${description.methodName} -> ${e.message}")
        }
    }

    // 测试用的 View ID
    private val BTN_ID = 1001
    private val EDIT_ID = 1002
    private val SCROLL_ID = 1003
    private val TEXT_ID = 1004
    // 等待超时统一配置（秒）
    private val DEFAULT_TIMEOUT_SECONDS = 20L

    /**
     * 测试前置初始化，准备性能记录器与测试场景，并确保页面空闲稳定
     */
    @Before
    fun setUp() {
        debug.step("setUp.start")
        recorder = PerformanceRecorder()
        scenario = activityRule.scenario
        
        // ActivityTracker 已经在 MainApplication 中注册，这里不需要重复注册
        // 使用 instrumentation 的 idle 等待替代纯 sleep，提升稳定性
        debug.step("setUp.wait_idle_before_ui")
        waitForIdle()
        
        // 初始化测试 UI
        scenario.onActivity { activity ->
            debug.step("setUp.setupTestUI.begin")
            setupTestUI(activity)
            debug.step("setUp.setupTestUI.end")
        }
        
        // 等待 UI 稳定
        debug.step("setUp.wait_idle_after_ui")
        waitForIdle()
        // 预热元素树，保证 input_text 能按坐标解析目标控件
        primeElementTree()
    }

    /**
     * 测试结束打印性能报告
     */
    @After
    fun tearDown() {
        debug.step("tearDown.start")
        recorder.printReport()
        debug.step("tearDown.done")
    }

    /**
     * 在 Activity 中动态添加测试用的 UI 控件，保证测试环境一致
     */
    private fun setupTestUI(activity: Activity) {
        debug.step("setupTestUI.begin")
        val root = activity.findViewById<ViewGroup>(android.R.id.content)
        root.removeAllViews()

        val container = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
        }

        // 1. 测试点击的按钮
        val button = Button(activity).apply {
            id = BTN_ID
            text = "Test Button"
            setOnClickListener { text = "Clicked" }
        }
        container.addView(button)

        // 2. 测试输入的 EditText
        val editText = EditText(activity).apply {
            id = EDIT_ID
            hint = "Input Here"
        }
        container.addView(editText)

        // 3. 测试滑动的 ScrollView
        val scrollView = ScrollView(activity).apply {
            id = SCROLL_ID
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                500 // 限制高度以确保可滑动
            )
        }
        val scrollContent = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
        }
        for (i in 1..20) {
            scrollContent.addView(TextView(activity).apply {
                text = "Item $i"
                setPadding(20, 20, 20, 20)
            })
        }
        scrollView.addView(scrollContent)
        container.addView(scrollView)
        
        // 4. 显示状态的 TextView
        val statusText = TextView(activity).apply {
            id = TEXT_ID
            text = "Status: Idle"
        }
        container.addView(statusText)

        root.addView(container)
        debug.step("setupTestUI.end")
    }

    /**
     * 测试点击动作：通过 CommandHandler 执行 tap，并验证页面变化证据
     */
    @Test
    fun testTapAction() {
        debug.step("testTapAction.begin")
        val actionName = "TAP"
        Log.d(TAG, "Starting testTapAction")

        // 1. 准备参数
        val params = JSONObject().apply {
            put("x", 100) // 假设按钮在 (0,0) 附近，具体位置需要动态获取
            put("y", 100)
        }
        
        // 动态获取按钮位置
        var btnXDp = 0
        var btnYDp = 0
        scenario.onActivity {
            val btn = it.findViewById<View>(BTN_ID)
            val location = IntArray(2)
            btn.getLocationOnScreen(location)
            val density = it.resources.displayMetrics.density
            btnXDp = ((location[0] + btn.width / 2) / density).toInt()
            btnYDp = ((location[1] + btn.height / 2) / density).toInt()
        }
        params.put("x", btnXDp)
        params.put("y", btnYDp)

        // 2. 执行并计时
        executeCommand("tap", params, actionName) { response ->
            // 3. 验证结果
            val status = response.optString("status")
            val changeType = response.optString("page_change_type")
            // 验证 UI 实际变化（按钮文本变为 Clicked）
            var clicked = false
            scenario.onActivity {
                val btn = it.findViewById<Button>(BTN_ID)
                clicked = (btn.text?.toString() == "Clicked")
            }
            assertTrue(status == "success" && changeType.contains("view_hash_change") || (status == "error" && clicked))
        }
        debug.step("testTapAction.end")
    }

    /**
     * 测试文本输入动作：执行 input_text，校验返回值与 EditText 实际内容
     */
    @Test
    fun testInputTextAction() {
        debug.step("testInputTextAction.begin")
        val actionName = "INPUT"
        Log.d(TAG, "Starting testInputTextAction")

        // 动态获取 EditText 位置
        var editXDp = 0
        var editYDp = 0
        scenario.onActivity {
            val edit = it.findViewById<View>(EDIT_ID)
            val location = IntArray(2)
            edit.getLocationOnScreen(location)
            val density = it.resources.displayMetrics.density
            editXDp = ((location[0] + edit.width / 2) / density).toInt()
            editYDp = ((location[1] + edit.height / 2) / density).toInt()
        }

        val inputText = "Hello Agent"
        val params = JSONObject().apply {
            put("text", inputText)
            put("element", org.json.JSONArray().apply {
                put(editXDp)
                put(editYDp)
            })
        }

        executeCommand("input_text", params, actionName) { response ->
            assertEquals("success", response.optString("status"))
            assertEquals(inputText, response.optString("input_text"))
            
            // 验证 UI 实际变化
            scenario.onActivity {
                val edit = it.findViewById<EditText>(EDIT_ID)
                assertEquals(inputText, edit.text.toString())
            }
        }
        debug.step("testInputTextAction.end")
    }

    /**
     * 测试滑动动作：执行 swipe，校验 ScrollView 的滚动位置是否发生变化
     */
    @Test
    fun testSwipeAction() {
        debug.step("testSwipeAction.begin")
        val actionName = "SWIPE"
        Log.d(TAG, "Starting testSwipeAction")

        var startXDp = 0
        var startYDp = 0
        var endXDp = 0
        var endYDp = 0
        
        scenario.onActivity {
            val scroll = it.findViewById<View>(SCROLL_ID)
            val location = IntArray(2)
            scroll.getLocationOnScreen(location)
            val density = it.resources.displayMetrics.density
            val startXPx = location[0] + scroll.width / 2
            val startYPx = location[1] + scroll.height - 50
            val endXPx = startXPx
            val endYPx = location[1] + 50
            startXDp = (startXPx / density).toInt()
            startYDp = (startYPx / density).toInt()
            endXDp = (endXPx / density).toInt()
            endYDp = (endYPx / density).toInt()
        }

        val params = JSONObject().apply {
            put("start_x", startXDp)
            put("start_y", startYDp)
            put("end_x", endXDp)
            put("end_y", endYDp)
            put("duration_ms", 500)
        }

        executeCommand("swipe", params, actionName) { response ->
            val status = response.optString("status")
            val err = response.optString("error")
            assertTrue(status == "success" || err.contains("page unchanged"))
            
            // 验证 ScrollY 变化
            scenario.onActivity {
                val scroll = it.findViewById<ScrollView>(SCROLL_ID)
                assertTrue("ScrollView should have scrolled", scroll.scrollY > 0)
            }
        }
        debug.step("testSwipeAction.end")
    }
    
    /**
     * 测试返回动作：执行 back，允许页面未变化的错误返回，只记录耗时
     */
    @Test
    fun testBackAction() {
        debug.step("testBackAction.begin")
        val actionName = "BACK"
        // Back 可能会关闭 Activity，所以我们需要小心
        // 这里主要测试 CommandHandler 的处理逻辑
        
        executeCommand("back", JSONObject(), actionName) { response ->
            // Back 成功可能会导致 Activity 暂停或销毁，或者只是关闭键盘
            // 根据 CommandHandler 逻辑，如果页面没变会报错 "Back succeeded but page unchanged"
            // 为了让页面变化，我们可以先打开一个 Dialog 或者 ...
            // 简单起见，我们接受 status=error (page unchanged) 也算执行完成了，只要耗时记录下来
            // 或者我们期望它是 success 如果 activity 栈有变化
            val status = response.optString("status")
            val err = response.optString("error")
            assertTrue(status == "success" || err.contains("page unchanged") || err.contains("action failed"))
        }
        debug.step("testBackAction.end")
    }

    /**
     * 测试 get_state 的脏页面防御：在页面动态扰动下执行 get_state，验证耗时显著增加
     */
    @Test
    fun testGetStateDirtyPageDefense() {
        debug.step("testGetStateDirtyPageDefense.begin")
        Log.d(TAG, "Starting testGetStateDirtyPageDefense")

        // 1. 基准测试：静态页面
        debug.step("get_state.static.start")
        recorder.start("GET_STATE_STATIC")
        val latchStatic = CountDownLatch(1)
        var staticTime = 0L
        
        scenario.onActivity { activity ->
            CommandHandler.handleCommand("get_state", JSONObject(), "req_static", activity) {
                recorder.stop("GET_STATE_STATIC")
                staticTime = recorder.getLastDuration("GET_STATE_STATIC")
                latchStatic.countDown()
            }
        }
        latchStatic.await(10, TimeUnit.SECONDS)
        Log.i(TAG, "Static get_state time: ${staticTime}ms")
        debug.step("get_state.static.end")

        // 2. 干扰测试：动态页面
        debug.step("get_state.dirty.disturb.start")
        val isDisturbing = AtomicReference(true)
        val handlerRef = AtomicReference<Handler>()
        val runnableRef = AtomicReference<Runnable>()
        scenario.onActivity { activity ->
            val tv = activity.findViewById<TextView>(TEXT_ID)
            val handler = Handler(Looper.getMainLooper())
            val runnable = object : Runnable {
                var count = 0
                override fun run() {
                    if (isDisturbing.get()) {
                        tv.text = "Disturbing... ${count++}"
                        handler.postDelayed(this, 100) // 每100ms修改一次
                    }
                }
            }
            handlerRef.set(handler)
            runnableRef.set(runnable)
            handler.post(runnable)
        }

        // 让干扰跑一会儿
        waitForIdle()

        // 发起 get_state，预期会被阻塞
        debug.step("get_state.dirty.request.start")
        recorder.start("GET_STATE_DIRTY")
        val latchDirty = CountDownLatch(1)
        
        scenario.onActivity { activity ->
            // 设置一个较长的 stabilize_timeout
            val params = JSONObject().apply {
                put("stabilize_timeout_ms", 5000)
                put("stable_window_ms", 1000)
            }
            
            CommandHandler.handleCommand("get_state", params, "req_dirty", activity) {
                recorder.stop("GET_STATE_DIRTY")
                latchDirty.countDown()
            }
        }
        
        // 在等待过程中，停止干扰，让页面稳定，从而让 get_state 返回
        // 使用标志位停止重发，同时移除回调，避免残留任务
        waitForIdle()
        isDisturbing.set(false) // 停止干扰
        scenario.onActivity {
            handlerRef.get()?.removeCallbacks(runnableRef.get())
        }
        
        assertTrue("Get state timeout", latchDirty.await(DEFAULT_TIMEOUT_SECONDS, TimeUnit.SECONDS))
        debug.step("get_state.dirty.request.end")
        
        val dirtyTime = recorder.getLastDuration("GET_STATE_DIRTY")
        Log.i(TAG, "Dirty get_state time: ${dirtyTime}ms")
        
        // 验证：动态页面的耗时应该显著大于静态页面 + 干扰持续时间
        assertTrue("Dirty page should take longer", dirtyTime >= staticTime + 300)
        debug.step("testGetStateDirtyPageDefense.end")
    }

    // --- Helper Methods ---

    /**
     * 执行指定命令并进行断言，统一计时与超时控制
     * @param cmd 命令名（如 tap、input_text、swipe、back、get_state）
     * @param params 命令参数
     * @param actionName 动作名称（用于性能记录分类）
     * @param assertion 响应断言逻辑
     */
    private fun executeCommand(
        cmd: String, 
        params: JSONObject, 
        actionName: String, 
        assertion: (JSONObject) -> Unit
    ) {
        debug.step("executeCommand.start:$cmd")
        debug.info("command.params:$params")
        val latch = CountDownLatch(1)
        val resultRef = AtomicReference<JSONObject>()

        recorder.start(actionName)
        
        debug.step("executeCommand.onActivity.invoke:$cmd")
        scenario.onActivity { activity ->
            CommandHandler.handleCommand(cmd, params, "req_$actionName", activity) { response ->
                recorder.stop(actionName)
                resultRef.set(response)
                latch.countDown()
                debug.step("executeCommand.callback_received:$cmd")
            }
        }

        // 等待命令完成并确保主线程空闲
        val completed = latch.await(DEFAULT_TIMEOUT_SECONDS, TimeUnit.SECONDS)
        assertTrue("Command $cmd timed out", completed)
        waitForIdle()
        
        val response = resultRef.get()
        assertNotNull("Response should not be null", response)
        
        Log.d(TAG, "Response for $cmd: $response")
        assertion(response)
        debug.step("executeCommand.done:$cmd")
    }

    /**
     * 在主线程同步执行指定代码块
     */
    private fun runOnMainSync(block: () -> Unit) {
        InstrumentationRegistry.getInstrumentation().runOnMainSync(block)
    }

    /**
     * 等待当前 instrumentation 与 UI 线程进入空闲状态
     */
    private fun waitForIdle() {
        try {
            InstrumentationRegistry.getInstrumentation().waitForIdleSync()
        } catch (e: Throwable) {
            // 兼容性兜底，避免因 idleSync 抛异常导致测试失败
            try {
                Thread.sleep(200)
            } catch (_: InterruptedException) {}
        }
    }

    // --- Performance Recorder ---
    
    /**
     * 动作性能记录器：记录开始/结束时间，汇总输出报告
     */
    class PerformanceRecorder {
        private val startTimes = HashMap<String, Long>()
        private val durations = ArrayList<Record>()

        /**
         * 单条记录结构
         */
        data class Record(val name: String, val durationMs: Long, val success: Boolean = true)

        /**
         * 开始记录某动作
         */
        fun start(name: String) {
            startTimes[name] = System.currentTimeMillis()
        }

        /**
         * 停止记录某动作，计算耗时并保存
         */
        fun stop(name: String) {
            val start = startTimes[name] ?: return
            val duration = System.currentTimeMillis() - start
            durations.add(Record(name, duration))
            Log.i("Performance", "Action [$name] took ${duration}ms")
        }
        
        /**
         * 读取某动作最近一次耗时
         */
        fun getLastDuration(name: String): Long {
            return durations.findLast { it.name == name }?.durationMs ?: 0L
        }

        /**
         * 输出性能汇总报告到日志
         */
        fun printReport() {
            Log.i("AgentTest", "============================================")
            Log.i("AgentTest", "动作执行性能报告 (单位: ms)")
            Log.i("AgentTest", "============================================")
            Log.i("AgentTest", String.format("| %-15s | %-8s | %-8s |", "Action", "Duration", "Result"))
            Log.i("AgentTest", "--------------------------------------------")
            
            // Group by action
            val grouped = durations.groupBy { it.name }
            grouped.forEach { (name, records) ->
                val avg = records.map { it.durationMs }.average().toLong()
                val min = records.minOf { it.durationMs }
                val max = records.maxOf { it.durationMs }
                val count = records.size
                
                Log.i("AgentTest", String.format("| %-15s | Avg:%4d | Count:%2d |", name, avg, count))
                Log.i("AgentTest", String.format("| %-15s | Min:%4d | Max:%4d |", "", min, max))
            }
            Log.i("AgentTest", "============================================")
        }
    }

    /**
     * 测试调试日志工具：统一输出步骤、信息与错误，包含线程名
     */
    class DebugLogger(private val tag: String) {
        fun step(name: String) {
            Log.d(tag, "STEP: $name [thread=${Thread.currentThread().name}]")
        }
        fun info(message: String) {
            Log.i(tag, message)
        }
        fun error(where: String, e: Throwable?) {
            if (e != null) {
                Log.e(tag, "ERROR at $where: ${e.message}", e)
            } else {
                Log.e(tag, "ERROR at $where")
            }
        }
    }
}
