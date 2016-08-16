FLAGS=-pthread -std=c++11 -pedantic
ASIO_FLAGS=-DASIO_STANDALONE -I./dependencies/asio-1.10.6/include
BUILD_FLAGS=-fPIC -DGENERATE_LIB

all: build/librstats.so

build/rstats.o: ./src/rstats.cpp ./src/rstats.h ./src/syslog.h
	g++ ${FLAGS} ${ASIO_FLAGS} ${BUILD_FLAGS} -c $< -o $@

build/librstats.so: ./build/rstats.o
	g++ -shared ${FLAGS} -o $@ $<
 
install: all
	cp build/librstats.so src/*.h $(if ${DESTDIR}, ${DESTDIR}, .)

clean:
	@rm -f *.o
	@rm -f *.so
