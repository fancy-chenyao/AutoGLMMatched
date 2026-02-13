package com.example.emplab

import Agent.ActivityTracker
import android.app.Application

class MainApplication : Application() {
    /**
     * 应用启动入口：注册 ActivityTracker 并输出启动日志，便于定位是否进入应用进程
     */
    override fun onCreate() {
        super.onCreate()
        ActivityTracker.register(this)
        android.util.Log.i("MainApplication", "App started for instrumentation, sdk=${android.os.Build.VERSION.SDK_INT}")
    }
}
