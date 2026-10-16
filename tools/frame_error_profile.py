"""Spatial RGB error diagnostics for two equal-size CPS-1 RGBA frames.

No graphics ROMs or external dependencies. The report is descriptive and
is not evidence of parity with actual arcade gameplay.
"""


def profile_rgba(reference, candidate, width=384, height=224):
    if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
        raise ValueError('Invalid frame geometry')
    count = width * height
    if len(reference) != count*4 or len(candidate) != count*4:
        raise ValueError('Two RGBA images of the same size required')
    rows = [0] * height
    columns = [0] * width
    channel_pixels = [0, 0, 0]
    channel_error_totals = [0, 0, 0]
    quadrants = [0, 0, 0, 0]
    low_x, low_y = width, height
    high_x, high_y = -1, -1
    for y in range(height):
        for x in range(width):
            base = 4*(y*width+x)
            errors = [abs(reference[base+c]-candidate[base+c]) for c in range(3)]
            for c, error in enumerate(errors):
                channel_error_totals[c] += error
                if error:
                    channel_pixels[c] += 1
            if any(errors):
                rows[y] += 1
                columns[x] += 1
                quadrants[int(y >= height//2)*2+int(x >= width//2)] += 1
                low_x, low_y = min(low_x,x), min(low_y,y)
                high_x, high_y = max(high_x,x), max(high_y,y)
    total = sum(rows)
    return {
        'width': width, 'height': height,
        'different_rgb_pixels': total,
        'bounding_box_xyxy_inclusive': [low_x,low_y,high_x,high_y] if total else None,
        'rows_with_errors': sum(v>0 for v in rows),
        'columns_with_errors': sum(v>0 for v in columns),
        'max_errors_in_one_row': max(rows),
        'row_mismatch_counts': rows,
        'column_mismatch_counts': columns,
        'rgb_channels_with_mismatches': dict(zip(('R','G','B'),channel_pixels)),
        'rgb_absolute_error_totals': dict(zip(('R','G','B'),channel_error_totals)),
        'quadrant_mismatches_TL_TR_BL_BR': quadrants,
        'interpretation': 'diagnostic_only_not_game_wide_parity',
    }
