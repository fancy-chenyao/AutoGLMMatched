package Agent

import android.app.Application
import android.content.ContentProvider
import android.content.ContentValues
import android.database.Cursor
import android.net.Uri
import android.util.Log

class AgentInitProvider : ContentProvider() {

    /**
     * Provider创建时的初始化入口
     * 在进程安装Provider阶段自动调用，注册ActivityTracker以监听Activity生命周期
     * @return 初始化是否成功
     */
    override fun onCreate(): Boolean {
        return try {
            val app = context?.applicationContext as Application
            ActivityTracker.register(app)
            Log.i("AgentInitProvider", "ActivityTracker registered via ContentProvider")
            true
        } catch (e: Exception) {
            Log.e("AgentInitProvider", "Initialization failed: ${e.message}")
            false
        }
    }

    /**
     * 查询方法占位实现
     * 初始化型Provider不提供数据访问能力
     */
    override fun query(
        uri: Uri,
        projection: Array<out String>?,
        selection: String?,
        selectionArgs: Array<out String>?,
        sortOrder: String?
    ): Cursor? = null

    /**
     * 返回MIME类型占位实现
     * 初始化型Provider不暴露数据类型
     */
    override fun getType(uri: Uri): String? = null

    /**
     * 插入方法占位实现
     * 初始化型Provider不支持插入操作
     */
    override fun insert(uri: Uri, values: ContentValues?): Uri? = null

    /**
     * 删除方法占位实现
     * 初始化型Provider不支持删除操作
     */
    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?): Int = 0

    /**
     * 更新方法占位实现
     * 初始化型Provider不支持更新操作
     */
    override fun update(
        uri: Uri,
        values: ContentValues?,
        selection: String?,
        selectionArgs: Array<out String>?
    ): Int = 0
}

