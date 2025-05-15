pip install --upgrade pip
pip install pdf2image


# Generate DocTags for all pages and run the visualizer
python doctags_gen.py --pdf document.pdf --output results/ && python create_index.py --directory results/

python analyzer.py --image document.pdf --page 13

python visualizer.py --doctags output.doctags.txt --pdf document.pdf --page 13 --adjust --show


python analyzer.py --image document.pdf --page 13 && python visualizer.py --doctags output.doctags.txt --pdf document.pdf --page 13 --adjust --show



## Run full with scaling fix
python analyzer.py --image document.pdf --page 7 && python fix_scaling.py --doctags output.doctags.txt --output fixed_output.doctags.txt --x-factor 0.7 --y-factor 0.7 && python visualizer.py --doctags fixed_output.doctags.txt --pdf document.pdf --page 7 --adjust --show