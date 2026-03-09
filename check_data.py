#!/usr/bin/env python3
from budget_cell.excel_io import read_rows_from_excel_path
from budget_cell.trend import rows_to_trend_nodes
from budget_cell.matchers import MATCHERS

r6_rows = read_rows_from_excel_path('R6/bugget_spread_cover1_long_v3.xlsx')
r8_rows = read_rows_from_excel_path('R8/bugget_setsumei_long_ffill.xlsx')

print(f'R6 rows: {len(r6_rows)}')
print(f'R8 rows: {len(r8_rows)}')

r6_nodes = rows_to_trend_nodes('R6', r6_rows)
r8_nodes = rows_to_trend_nodes('R8', r8_rows)

print(f'R6 nodes: {len(r6_nodes)}')
print(f'R8 nodes: {len(r8_nodes)}')

# Find議会費 nodes from both years
print('\n=== R6 議会費 samples ===')
for n in r6_nodes:
    if '議会費' in n.key.moku_name:
        print(f'  moku={repr(n.key.moku_name)} name={repr(n.setsumei_name)}')
        break

print('\n=== R8 議会費 samples ===')
for n in r8_nodes:
    if '議会費' in n.key.moku_name:
        print(f'  moku={repr(n.key.moku_name)} name={repr(n.setsumei_name)}')
        break

# Check strict vs loose for a specific key
strict = MATCHERS['strict']
loose = MATCHERS['loose']

print('\n=== R6 first 5 match IDs ===')
for n in r6_nodes[:5]:
    print(f'  strict: {strict(n.key)[:60]}')
    print(f'  loose:  {loose(n.key)[:60]}')
    print()

print('\n=== R8 first 5 match IDs ===')
for n in r8_nodes[:5]:
    print(f'  strict: {strict(n.key)[:60]}')
    print(f'  loose:  {loose(n.key)[:60]}')
    print()
