package si.jakob.rtxskener

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

class Db private constructor(ctx: Context) : SQLiteOpenHelper(ctx, "rtx_skener.db", null, 1) {

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            "CREATE TABLE oglasi (url TEXT PRIMARY KEY, vir TEXT, model TEXT, naslov TEXT, " +
                "cena REAL, prvic INTEGER, opozorjeno INTEGER DEFAULT 0, ponovitev INTEGER DEFAULT 0, " +
                "trg REAL, zasluzek REAL)"
        )
        db.execSQL("CREATE INDEX idx_model ON oglasi(model)")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {}

    companion object {
        @Volatile
        private var inst: Db? = null

        fun get(ctx: Context): Db =
            inst ?: synchronized(this) { inst ?: Db(ctx.applicationContext).also { inst = it } }
    }
}
