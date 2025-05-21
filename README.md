# DocTags Analyzer and Visualizer

Simple command to process PDF pages with DocTags:

```bash
python analyzer.py --image document.pdf --page 8 && python visualizer.py --doctags results/output.doctags.txt --pdf document.pdf --page 8 --adjust && python picture_extractor.py --doctags results/output.doctags.txt --pdf document.pdf --page 8 --adjust
```

All output files will be automatically stored in the `results` folder.