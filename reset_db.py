import sqlite3

conn = sqlite3.connect('expenses.db')
cur = conn.cursor()

cur.execute('DELETE FROM expenses')
print('Expenses deleted:', cur.rowcount)

cur.execute('DELETE FROM balance_adjustments')
print('Adjustments deleted:', cur.rowcount)

cur.execute('DELETE FROM accounts')
print('Accounts deleted:', cur.rowcount)

# Reset auto-increment counters so IDs start from 1
cur.execute("DELETE FROM sqlite_sequence WHERE name='expenses'")
cur.execute("DELETE FROM sqlite_sequence WHERE name='accounts'")
cur.execute("DELETE FROM sqlite_sequence WHERE name='balance_adjustments'")

conn.commit()
conn.close()

conn2 = sqlite3.connect('expenses.db')
cur2 = conn2.cursor()
cur2.execute('SELECT COUNT(*) FROM expenses')
print('Expenses remaining:', cur2.fetchone()[0])
cur2.execute('SELECT COUNT(*) FROM accounts')
print('Accounts remaining:', cur2.fetchone()[0])
cur2.execute('SELECT COUNT(*) FROM balance_adjustments')
print('Adjustments remaining:', cur2.fetchone()[0])
conn2.close()
print('All test/seed data wiped. Database is clean and ready!')

