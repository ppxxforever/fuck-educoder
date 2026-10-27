n = int(input())
rows = []
for i in range(n):
    row = [1] * (i + 1)
    for j in range(1, i):
        row[j] = rows[i - 1][j - 1] + rows[i - 1][j]
    rows.append(row)

width = 5
for i in range(n):
    line = ""
    for num in rows[i]:
        line += str(num).rjust(width)
    print(line.rjust(width * n))