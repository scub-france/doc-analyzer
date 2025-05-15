#!/usr/bin/env python3
"""
DocTags Scaling Fix - Script to fix scaling issues in the DocTags visualizer.

Usage:
    python fix_scaling.py --doctags output.doctags.txt --output fixed_output.doctags.txt
"""

import argparse
import re
import sys
from pathlib import Path
import json

# Regular expression to extract location data
LOC_PATTERN = r'<loc_(\d+)><loc_(\d+)><loc_(\d+)><loc_(\d+)>'

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Fix scaling issues in DocTags output')
    parser.add_argument('--doctags', '-d', type=str, required=True,
                        help='Path to original DocTags file')
    parser.add_argument('--output', '-o', type=str, required=True,
                        help='Path to save the fixed DocTags file')
    parser.add_argument('--x-factor', '-x', type=float, default=0.7,
                        help='X-axis scaling factor (default: 0.7)')
    parser.add_argument('--y-factor', '-y', type=float, default=0.7,
                        help='Y-axis scaling factor (default: 0.7)')
    parser.add_argument('--x-offset', type=int, default=0,
                        help='X-axis offset (default: 0)')
    parser.add_argument('--y-offset', type=int, default=0,
                        help='Y-axis offset (default: 0)')
    return parser.parse_args()

def read_doctags_file(doctags_path):
    """Read the DocTags file."""
    with open(doctags_path, 'r', encoding='utf-8') as f:
        return f.read()

def write_doctags_file(content, output_path):
    """Write the fixed DocTags file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Fixed DocTags saved to: {output_path}")

def fix_scaling(doctags_content, x_factor, y_factor, x_offset, y_offset):
    """Apply scaling factors to all location tags in the DocTags content."""
    def apply_scaling(match):
        x1, y1, x2, y2 = map(int, match.groups())

        # Apply scaling and offset
        new_x1 = int(x1 * x_factor) + x_offset
        new_y1 = int(y1 * y_factor) + y_offset
        new_x2 = int(x2 * x_factor) + x_offset
        new_y2 = int(y2 * y_factor) + y_offset

        # Ensure coordinates are positive
        new_x1 = max(0, new_x1)
        new_y1 = max(0, new_y1)
        new_x2 = max(0, new_x2)
        new_y2 = max(0, new_y2)

        return f"<loc_{new_x1}><loc_{new_y1}><loc_{new_x2}><loc_{new_y2}>"

    # Apply the scaling to all location tags
    fixed_content = re.sub(LOC_PATTERN, apply_scaling, doctags_content)

    # Count how many replacements were made
    original_matches = re.findall(LOC_PATTERN, doctags_content)
    fixed_matches = re.findall(LOC_PATTERN, fixed_content)

    print(f"Modified {len(original_matches)} location tags")

    # Print before/after sample for the first few zones
    if original_matches and fixed_matches:
        print("\nBefore/After comparison (first 3 zones):")
        for i, (orig, fixed) in enumerate(zip(original_matches, fixed_matches)):
            if i >= 3:
                break
            orig_x1, orig_y1, orig_x2, orig_y2 = map(int, orig)
            fixed_x1, fixed_y1, fixed_x2, fixed_y2 = map(int, fixed_matches[i])
            print(f"Zone {i+1}: ({orig_x1},{orig_y1},{orig_x2},{orig_y2}) → ({fixed_x1},{fixed_y1},{fixed_x2},{fixed_y2})")

    return fixed_content

def analyze_doctags(doctags_content):
    """Analyze the DocTags content to suggest scaling factors."""
    # Find all location tags
    locations = re.findall(LOC_PATTERN, doctags_content)

    if not locations:
        print("No location tags found in the DocTags file.")
        return

    # Extract coordinates
    coords = [(int(x1), int(y1), int(x2), int(y2)) for x1, y1, x2, y2 in locations]

    # Find the boundaries
    min_x = min(min(x1, x2) for x1, y1, x2, y2 in coords)
    min_y = min(min(y1, y2) for x1, y1, x2, y2 in coords)
    max_x = max(max(x1, x2) for x1, y1, x2, y2 in coords)
    max_y = max(max(y1, y2) for x1, y1, x2, y2 in coords)

    # Calculate average zone size
    avg_width = sum(abs(x2 - x1) for x1, y1, x2, y2 in coords) / len(coords)
    avg_height = sum(abs(y2 - y1) for x1, y1, x2, y2 in coords) / len(coords)

    print("\nDocTags Analysis:")
    print(f"Found {len(locations)} zones with coordinates")
    print(f"Coordinate boundaries: X({min_x}-{max_x}), Y({min_y}-{max_y})")
    print(f"Average zone size: {avg_width:.1f} x {avg_height:.1f}")

    # Suggest appropriate scaling for standard page sizes
    a4_width, a4_height = 595, 842  # A4 in points

    # Calculate suggested scaling to fit A4
    x_factor = a4_width / max_x if max_x > 0 else 1.0
    y_factor = a4_height / max_y if max_y > 0 else 1.0

    # Apply some heuristics for common scaling issues
    if max_x > 1000 and max_y > 1000:
        print("\nDetected large coordinates - typical of high-resolution scans or OCR")
        print("Suggested scaling factors for standard page:")
        print(f"X-factor: {x_factor:.3f} (to fit width to A4)")
        print(f"Y-factor: {y_factor:.3f} (to fit height to A4)")
    elif max_x < 300 and max_y < 300:
        print("\nDetected small coordinates - might be normalized values")
        print("Suggested scaling factors for standard page:")
        print(f"X-factor: {a4_width/300:.3f} (to expand to A4 width)")
        print(f"Y-factor: {a4_height/300:.3f} (to expand to A4 height)")

    # Check for pattern inconsistencies (possible corruption or bad parsing)
    widths = [abs(x2 - x1) for x1, y1, x2, y2 in coords]
    heights = [abs(y2 - y1) for x1, y1, x2, y2 in coords]
    width_std_dev = (sum((w - avg_width) ** 2 for w in widths) / len(widths)) ** 0.5
    height_std_dev = (sum((h - avg_height) ** 2 for h in heights) / len(heights)) ** 0.5

    if width_std_dev > avg_width * 1.5 or height_std_dev > avg_height * 1.5:
        print("\nWarning: High variance in zone sizes detected!")
        print("This might indicate inconsistent scaling or parsing issues.")

    return {
        'min_x': min_x, 'max_x': max_x, 'min_y': min_y, 'max_y': max_y,
        'avg_width': avg_width, 'avg_height': avg_height,
        'suggested_x_factor': x_factor, 'suggested_y_factor': y_factor
    }

def main():
    args = parse_arguments()

    # Read the original DocTags file
    try:
        doctags_content = read_doctags_file(args.doctags)
        print(f"Read DocTags file: {args.doctags} ({len(doctags_content)} bytes)")
    except Exception as e:
        print(f"Error reading DocTags file: {e}")
        return 1

    # Analyze the DocTags content
    analysis = analyze_doctags(doctags_content)

    # Confirm with user
    if not analysis:
        print("No analysis could be performed. Using specified scaling factors.")
    else:
        print(f"\nYou specified x-factor={args.x_factor}, y-factor={args.y_factor}")
        print(f"Analysis suggests x-factor={analysis.get('suggested_x_factor', 1.0):.3f}, "
              f"y-factor={analysis.get('suggested_y_factor', 1.0):.3f}")

        use_suggested = input("\nUse suggested scaling factors instead? [y/N]: ").lower()
        if use_suggested.startswith('y'):
            args.x_factor = analysis.get('suggested_x_factor', args.x_factor)
            args.y_factor = analysis.get('suggested_y_factor', args.y_factor)
            print(f"Using suggested factors: x={args.x_factor:.3f}, y={args.y_factor:.3f}")

    # Apply the scaling fix
    try:
        fixed_content = fix_scaling(doctags_content, args.x_factor, args.y_factor,
                                    args.x_offset, args.y_offset)

        # Save the fixed DocTags file
        write_doctags_file(fixed_content, args.output)

        print("\nScaling fix complete!")
        print("Run visualizer with the fixed DocTags file:")
        print(f"python visualizer.py --doctags {args.output} --pdf your_document.pdf --page 1 --show")

        return 0
    except Exception as e:
        print(f"Error applying scaling fix: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())